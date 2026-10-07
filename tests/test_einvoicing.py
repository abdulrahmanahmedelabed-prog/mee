# -*- coding: utf-8 -*-
"""الفوترة الإلكترونية المرتبطة: «فاتورة» السعودية (المرحلة الثانية) و JoFotara الأردن — مع خادم وهمي يتحقق كما تتحقق المنصة"""

import base64
import datetime
import hashlib
import xml.etree.ElementTree as ET
import zlib

import pytest

pytest.importorskip("cryptography")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from core import db, einvoicing as E, products, receipts, sales, settings, financial_audit  # noqa: E402

KSA = {"einv_system": "zatca", "vat_enabled": "1", "vat_rate": "15", "prices_include_vat": "1",
       "tax_number": "399999999900003", "einv_crn": "1010010000", "einv_street": "شارع الملك فهد", "einv_building": "1234",
       "einv_district": "العليا", "einv_city": "الرياض", "einv_postal": "12345", "shop_name": "متجر & شركاه"}


def tlv(b64):
    raw, i, out = base64.b64decode(b64), 0, {}
    while i < len(raw):
        out[raw[i]] = raw[i + 2:i + 2 + raw[i + 1]]
        i += 2 + raw[i + 1]
    return out


class FakeZatca:
    """يصدر شهادات من طلب CSR ويتحقق من كل فاتورة: البصمة، التوقيع، QR، والسلسلة"""

    def __init__(self):
        self.ca_key = ec.generate_private_key(ec.SECP256K1())
        self.ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TSZEINVOICE-SubCA-1"),
                                  x509.NameAttribute(NameOID.DOMAIN_COMPONENT, "extgazt")])
        self.reported, self.calls = [], []

    def issue(self, csr_b64):
        csr = x509.load_pem_x509_csr(base64.b64decode(csr_b64))
        assert csr.is_signature_valid
        tmpl = csr.extensions.get_extension_for_oid(x509.ObjectIdentifier("1.3.6.1.4.1.311.20.2")).value.value
        assert tmpl == b"\x13\x15TSTZATCA-Code-Signing"
        san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dn = san.get_values_for_type(x509.DirectoryName)[0]
        assert dn.get_attributes_for_oid(NameOID.USER_ID)[0].value == "399999999900003"
        now = datetime.datetime.utcnow()
        cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(self.ca_name).public_key(csr.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=365)).sign(self.ca_key, hashes.SHA256()))
        body = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
        return base64.b64encode(body.encode()).decode()

    def check(self, body):
        xml = base64.b64decode(body["invoice"]).decode()
        root = ET.fromstring(xml.split("?>", 1)[1])
        assert E.invoice_hash(E.strip_for_hash(xml)) == body["invoiceHash"]
        ns = {"ds": "http://www.w3.org/2000/09/xmldsig#", "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
        assert root.find(".//ds:Reference[@Id='invoiceSignedData']/ds:DigestValue", ns).text == body["invoiceHash"]
        cert = x509.load_der_x509_certificate(base64.b64decode(root.find(".//ds:X509Certificate", ns).text))
        sig = base64.b64decode(root.find(".//ds:SignatureValue", ns).text)
        cert.public_key().verify(sig, base64.b64decode(body["invoiceHash"]), ec.ECDSA(hashes.SHA256()))
        qr = [d for d in root.iter("{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}EmbeddedDocumentBinaryObject")]
        t = tlv(qr[1].text)
        assert t[6].decode() == body["invoiceHash"] and t[2] == b"399999999900003" and len(t) == 9
        assert root.find("cbc:UUID", ns).text == body["uuid"]
        return root

    def __call__(self, url, body, headers, timeout=20):
        self.calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("/compliance"):
            assert headers["OTP"] == "123345"
            return 200, {"requestID": 1234, "binarySecurityToken": self.issue(body["csr"]), "secret": "s3cr3t"}
        if url.endswith("/compliance/invoices"):
            self.check(body)
            return 200, {"validationResults": {"status": "PASS", "errorMessages": [], "warningMessages": []}}
        if url.endswith("/production/csids"):
            assert body["compliance_request_id"] == "1234"
            return 200, {"requestID": 99, "binarySecurityToken": self.issue(self._last_csr), "secret": "prod"}
        if url.endswith("/reporting/single"):
            root = self.check(body)
            self.reported.append(root)
            return 200, {"reportingStatus": "REPORTED", "validationResults": {"status": "PASS", "errorMessages": [],
                                                                               "warningMessages": []}}
        raise AssertionError(url)


@pytest.fixture
def zatca(monkeypatch):
    settings.set_many(KSA)
    fake = FakeZatca()
    real_csr = E.generate_csr

    def gen(*a, **k):
        key, csr = real_csr(*a, **k)
        fake._last_csr = base64.b64encode(csr.encode()).decode()
        return key, csr
    monkeypatch.setattr(E, "generate_csr", gen)
    monkeypatch.setattr(E, "_http", fake)
    return fake


def _sell(pid, qty=3, price=5.75, **kw):
    return sales.create_sale([{"product_id": pid, "product_name": "حليب & لبن", "quantity": qty, "unit_price": price}], **kw)


def test_zatca_full_cycle(zatca):
    assert not E.check_setup()
    pid = products.add_product("حليب & لبن", "z1", "", 3, 5.75, 100, 0)
    first = _sell(pid, discount=1.0, round_up=True)                 # قبل الربط: تُجهّز وتُختم وتنتظر التوقيع
    r1 = E.for_invoice(first["invoice_id"])
    assert r1["status"] == "pending" and not r1["signed"] and r1["icv"] == 1 and r1["pih"] == E.INITIAL_PIH
    msg = E.zatca_onboard("123345")
    assert "تم الربط" in msg and E.zatca_stage() == "ready"
    assert E.for_invoice(first["invoice_id"])["signed"] == 1             # وُقّعت بعد الربط
    second = _sell(pid)
    r2 = E.for_invoice(second["invoice_id"])
    assert r2["signed"] and r2["icv"] == 2 and r2["pih"] == r1["hash"]   # سلسلة البصمات
    # الإيصال يطبع QR المرحلة الثانية
    assert E.receipt_qr_text(second["invoice_id"]) == r2["qr"]
    assert tlv(r2["qr"])[4].decode() == f"{second['total']:.2f}"
    # مرتجع ← إشعار دائن يشير للفاتورة الأصلية
    it = sales.returnable_items(second["invoice_id"])[0]
    ret = sales.create_return(second["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], reason="تالف")
    cn = db.query_one("SELECT * FROM einvoices WHERE return_id=?", (ret["return_id"],))
    xml = zlib.decompress(cn["xml"]).decode()
    assert ">381</cbc:InvoiceTypeCode>" in xml and second["invoice_number"] in xml and "تالف" in xml
    assert E.send_pending() == 3 and E.summary()["reported"] == 3
    # المبالغ: المستحق = المبلغ المدفوع فعلاً، والفرق (التقريب لأعلى) في PayableRoundingAmount
    root = zatca.reported[0]
    ns = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
          "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
    lm = root.find("cac:LegalMonetaryTotal", ns)
    v = {e.tag.split("}")[1]: float(e.text) for e in lm}
    assert abs(v["PayableAmount"] - first["total"]) < 0.001
    assert abs(v["TaxInclusiveAmount"] + v.get("PayableRoundingAmount", 0) - v["PayableAmount"]) < 0.001
    assert abs(v["TaxExclusiveAmount"] - (v["LineExtensionAmount"] - v["AllowanceTotalAmount"])) < 0.001


def test_offline_then_report_and_audit(zatca, monkeypatch):
    E.zatca_onboard("123345")
    pid = products.add_product("أرز", "z2", "", 3, 10, 100, 0)
    _sell(pid, 1, 10)

    def down(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(E, "_http", down)
    assert E.send_pending() == 0 and E.summary()["pending"] == 1          # البيع لا يتأثر؛ يبقى في الطابور
    with db.tx() as c:
        c.execute("UPDATE einvoices SET created_at = datetime('now','localtime','-2 days')")
    titles = {f["title"] for f in financial_audit.run(db.today(), db.today())["findings"]}
    assert "فواتير إلكترونية لم تُبلَّغ خلال 24 ساعة" in titles
    monkeypatch.setattr(E, "_http", zatca)
    assert E.send_pending() == 1


def test_sale_never_fails_because_of_einvoicing(monkeypatch):
    settings.set_many(KSA)
    monkeypatch.setattr(E, "_document", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    pid = products.add_product("سكر", "z3", "", 3, 10, 100, 0)
    res = _sell(pid, 1, 10)
    assert res["invoice_id"] and db.query_one("SELECT status FROM einvoices")["status"] == "error"


def test_jofotara(monkeypatch):
    settings.set_many({"einv_system": "jofotara", "vat_enabled": "1", "vat_rate": "16", "prices_include_vat": "1",
                       "tax_number": "12345678", "jof_client_id": "cid", "jof_source_id": "16683693", "shop_name": "بقالة"})
    E.set_jofotara_secret("sec")
    assert not E.check_setup()
    sent = []

    def fake(url, body, headers, timeout=20):
        assert url == E.JOFOTARA_URL and headers["Client-Id"] == "cid" and headers["Secret-Key"] == "sec"
        xml = base64.b64decode(body["invoice"]).decode()
        root = ET.fromstring(xml.split("?>", 1)[1])
        sent.append(root)
        return 200, {"EINV_STATUS": "SUBMITTED", "EINV_QR": "QRDATA" + str(len(sent)), "EINV_RESULTS": {"ERRORS": []}}
    monkeypatch.setattr(E, "_http", fake)
    pid = products.add_product("زيت", "j1", "", 3, 11.6, 100, 0)
    res = _sell(pid, 2, 11.6, discount=2.0)
    assert E.send_pending() == 1
    assert E.receipt_qr_text(res["invoice_id"]) == "QRDATA1"
    ns = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
          "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
    root = sent[0]
    assert root.find("cbc:InvoiceTypeCode", ns).attrib["name"] == "012"
    v = {e.tag.split("}")[1]: float(e.text) for e in root.find("cac:LegalMonetaryTotal", ns)}
    assert abs(v["PayableAmount"] - res["total"]) <= 0.02
    assert abs(v["TaxExclusiveAmount"] - v["AllowanceTotalAmount"] + float(root.find("cac:TaxTotal/cbc:TaxAmount", ns).text)
               - v["TaxInclusiveAmount"]) < 0.001
    html = receipts.invoice_html(res["invoice_id"])
    assert "data:image/png" in html or "QRDATA" not in html                # QR المنظومة يُطبع إن توفرت مكتبة qrcode


def test_jofotara_quick_send_before_print(monkeypatch):
    settings.set_many({"einv_system": "jofotara", "vat_enabled": "1", "vat_rate": "16", "tax_number": "12345678",
                       "jof_client_id": "cid", "jof_source_id": "1", "shop_name": "بقالة"})
    E.set_jofotara_secret("sec")
    monkeypatch.setattr(E, "_http", lambda *a, **k: (200, {"EINV_STATUS": "SUBMITTED", "EINV_QR": "OFFICIAL"}))
    pid = products.add_product("شاي", "j2", "", 3, 5, 100, 0)
    res = _sell(pid, 1, 5)
    assert E.quick_send(res["invoice_id"]) and E.receipt_qr_text(res["invoice_id"]) == "OFFICIAL"
    assert E.summary()["reported"] == 1

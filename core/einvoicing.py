# -*- coding: utf-8 -*-
"""
الفوترة الإلكترونية المرتبطة بمنصات الضريبة (اختيارية — تُفعَّل من الإعدادات):

• السعودية — «فاتورة» المرحلة الثانية (الربط والتكامل مع هيئة الزكاة والضريبة والجمارك):
  فاتورة UBL 2.1 لكل بيع ومرتجع (إشعار دائن)، بصمة SHA-256 مع سلسلة «بصمة الفاتورة السابقة» (PIH)
  وعدّاد الفواتير (ICV)، توقيع رقمي XAdES بمفتاح ECDSA (secp256k1) يُولَّد على جهاز المحل،
  رمز QR للمرحلة الثانية (9 حقول)، وربط الجهاز بالهيئة (طلب شهادة CSR + رمز OTP ← فحوص الامتثال ← شهادة الإنتاج)،
  ثم الإبلاغ عن الفواتير المبسطة في الخلفية (المهلة النظامية 24 ساعة).

• الأردن — نظام الفوترة الوطني (JoFotara) من دائرة ضريبة الدخل والمبيعات:
  فاتورة UBL 2.1 لكل بيع ومرتجع تُرسل بمعرّف العميل والرمز السري من بوابة JoFotara، ويُحفظ رمز QR الذي تعيده المنظومة
  ليُطبع على الفاتورة.

البيع لا يتوقف أبداً بسبب الفوترة: تُجهَّز الفاتورة وتُختم لحظة البيع وتُرسل عند توفر الإنترنت مع إعادة المحاولة.
"""

import base64
import hashlib
import json
import threading
import urllib.error
import urllib.request
import uuid as _uuid
import zlib
from datetime import datetime
from xml.sax.saxutils import escape

from core import db, settings
from core.utils import money

ZATCA, JOFOTARA = "zatca", "jofotara"
SYSTEMS = {"": "معطّلة", ZATCA: "السعودية — فاتورة (المرحلة الثانية)", JOFOTARA: "الأردن — نظام الفوترة الوطني (JoFotara)"}

ZATCA_ENVS = {
    "sandbox": ("بيئة المطورين (تجربة)", "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal", "TSTZATCA-Code-Signing"),
    "simulation": ("بيئة المحاكاة", "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation", "PREZATCA-Code-Signing"),
    "production": ("الإنتاج (الفعلي)", "https://gw-fatoora.zatca.gov.sa/e-invoicing/core", "ZATCA-Code-Signing"),
}
JOFOTARA_URL = "https://backend.jofotara.gov.jo/core/invoices/"
JO_KINDS = {"sales": "ضريبة مبيعات عامة", "income": "ضريبة دخل فقط (غير مسجّل في المبيعات)"}

# بصمة البداية المعتمدة لأول فاتورة في السلسلة = Base64(SHA256("0") بصيغة hex)
INITIAL_PIH = base64.b64encode(hashlib.sha256(b"0").hexdigest().encode()).decode()

STATUS = {"pending": "بانتظار الإرسال", "reported": "مُبلَّغ عنها", "warning": "مقبولة مع تنبيهات",
          "rejected": "مرفوضة", "error": "خطأ في التجهيز"}

NS_ROOT = ('xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
           'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
           'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
           'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"')

_LOCK = threading.Lock()
_SEND_LOCK = threading.Lock()


class EInvoiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# الإعدادات والأسرار (الأسرار في meta: تنتقل مع النسخة الاحتياطية ولا تظهر في الإعدادات العامة)
# ---------------------------------------------------------------------------

def system():
    s = settings.get("einv_system") or ""
    return s if s in SYSTEMS else ""


def enabled():
    return bool(system())


def _secrets():
    try:
        return json.loads(db.get_meta("einv_secrets") or "{}")
    except ValueError:
        return {}


def _save_secrets(d):
    db.set_meta("einv_secrets", json.dumps(d))


def set_jofotara_secret(secret):
    d = _secrets()
    d["jof_secret"] = (secret or "").strip()
    _save_secrets(d)


def has_jofotara_secret():
    return bool(_secrets().get("jof_secret"))


def zatca_stage():
    """none / compliance / ready"""
    d = _secrets().get("zatca", {})
    env = settings.get("einv_env") or "sandbox"
    if d.get("env") != env:
        return "none"
    if d.get("production", {}).get("token"):
        return "ready"
    if d.get("compliance", {}).get("token"):
        return "compliance"
    return "none"


def _x(v):
    return escape(str(v if v is not None else ""))


def _a(v):
    return _x(v).replace('"', "&quot;")


def _f2(v):
    return f"{money(v):.2f}"


def seller():
    """بيانات البائع من الإعدادات"""
    g = settings.get
    return {"name": g("einv_legal_name") or g("shop_name") or "", "vat": "".join(ch for ch in (g("tax_number") or "") if ch.isdigit()),
            "crn": g("einv_crn") or "", "street": g("einv_street") or "", "building": g("einv_building") or "",
            "district": g("einv_district") or "", "city": g("einv_city") or "", "postal": g("einv_postal") or "",
            "branch": g("branch_name") or g("shop_name") or "", "industry": g("einv_industry") or "Retail",
            "source": g("jof_source_id") or "", "client_id": g("jof_client_id") or ""}


def check_setup(sys_=None):
    """قائمة النواقص قبل التفعيل (فارغة = جاهز)"""
    sys_ = sys_ or system()
    s, miss = seller(), []
    if not s["name"]:
        miss.append("اسم المنشأة القانوني")
    if sys_ == ZATCA:
        if len(s["vat"]) != 15 or not (s["vat"].startswith("3") and s["vat"].endswith("3")):
            miss.append("الرقم الضريبي (15 رقماً يبدأ وينتهي بـ 3)")
        if not s["crn"]:
            miss.append("رقم السجل التجاري")
        if len(s["building"]) != 4 or not s["building"].isdigit():
            miss.append("رقم المبنى (4 أرقام)")
        if len(s["postal"]) != 5 or not s["postal"].isdigit():
            miss.append("الرمز البريدي (5 أرقام)")
        for k, lbl in (("street", "اسم الشارع"), ("district", "الحي"), ("city", "المدينة")):
            if not s[k]:
                miss.append(lbl)
        if not settings.get_bool("vat_enabled") or settings.get_float("vat_rate", 0) <= 0:
            miss.append("تفعيل ضريبة القيمة المضافة (15%) من إعدادات الضريبة")
    elif sys_ == JOFOTARA:
        if not s["vat"]:
            miss.append("الرقم الضريبي")
        if not s["source"]:
            miss.append("رقم تسلسل مصدر الدخل")
        if not s["client_id"] or not has_jofotara_secret():
            miss.append("معرّف العميل والرمز السري من بوابة JoFotara")
    return miss


# ---------------------------------------------------------------------------
# المستند: أسطر ومبالغ موحّدة من الفاتورة أو المرتجع
# ---------------------------------------------------------------------------

def _payment_code(inv):
    if inv["card_amount"] and inv["card_amount"] >= max(inv["cash_amount"], inv["wallet_amount"] or 0):
        return "48"                                     # بطاقة بنكية
    if (inv["wallet_amount"] or 0) > inv["cash_amount"]:
        return "30"                                     # تحويل إلكتروني
    if inv["credit_amount"] and inv["credit_amount"] >= inv["cash_amount"]:
        return "30"
    return "10"                                         # نقدي


def _document(kind, ref_id):
    """kind: invoice / credit. يرجع dict موحّداً للمستند"""
    rate = settings.get_float("vat_rate", 0) if settings.get_bool("vat_enabled") else 0.0
    inclusive = settings.get_bool("prices_include_vat")
    if kind == "invoice":
        inv = db.query_one("""SELECT i.*, c.name AS customer_name FROM invoices i
                              LEFT JOIN customers c ON c.id = i.customer_id WHERE i.id=?""", (ref_id,))
        if not inv:
            raise EInvoiceError("الفاتورة غير موجودة")
        items = db.query("SELECT product_name AS name, quantity, unit_price, unit_name FROM invoice_items WHERE invoice_id=? ORDER BY id",
                         (ref_id,))
        doc = {"kind": "invoice", "type_code": "388", "number": inv["invoice_number"], "issued": inv["created_at"],
               "total": inv["total"], "rounding": inv["rounding"] or 0, "payment": _payment_code(inv),
               "customer": inv["customer_name"] or "", "credit_sale": bool(inv["credit_amount"]), "invoice_id": ref_id,
               "return_id": None, "billing_ref": None, "reason": ""}
    else:
        r = db.query_one("""SELECT r.*, i.invoice_number, i.created_at AS inv_date, i.total AS inv_total, i.id AS inv_id,
                                   i.cash_amount, i.card_amount, i.credit_amount, i.wallet_amount, c.name AS customer_name
                            FROM returns r JOIN invoices i ON i.id = r.invoice_id
                            LEFT JOIN customers c ON c.id = i.customer_id WHERE r.id=?""", (ref_id,))
        if not r:
            raise EInvoiceError("المرتجع غير موجود")
        items = db.query("SELECT product_name AS name, quantity, unit_price, 'PCE' AS unit_name FROM return_items WHERE return_id=?",
                         (ref_id,))
        orig = db.query_one("SELECT uuid FROM einvoices WHERE invoice_id=? AND doc_type='invoice' AND system=?",
                            (r["inv_id"], system()))
        doc = {"kind": "credit", "type_code": "381", "number": r["return_number"], "issued": r["created_at"],
               "total": r["total"], "rounding": r["rounding"] or 0, "payment": _payment_code(r),
               "customer": r["customer_name"] or "", "credit_sale": bool(r["credit_amount"]), "invoice_id": r["inv_id"],
               "return_id": ref_id, "reason": r["reason"] or "إرجاع بضاعة",
               "billing_ref": {"number": r["invoice_number"], "date": (r["inv_date"] or "")[:10],
                               "uuid": orig["uuid"] if orig else "", "total": r["inv_total"]}}
    doc["lines"] = [{"name": i["name"], "qty": i["quantity"], "price": i["unit_price"]} for i in items]
    doc["rate"] = rate
    doc.update(_amounts(doc["lines"], doc["total"], doc["rounding"], rate, inclusive))
    return doc


def _amounts(lines, total, rounding, rate, inclusive):
    """مبالغ المستند بصيغة الفاتورة الإلكترونية: كل سطر بدون ضريبة، ثم الخصم، ثم الضريبة، والفرق في «التقريب»"""
    r = rate / 100.0
    out, line_sum, gross_sum = [], 0.0, 0.0
    for ln in lines:
        price = money(ln["price"] / (1 + r)) if inclusive and r else money(ln["price"])
        ext = money(ln["qty"] * price)
        out.append({"price": price, "ext": ext, "tax": money(ext * r)})
        line_sum += ext
        gross_sum += money(ln["qty"] * ln["price"])
    base = money(total - (rounding or 0))                    # المبلغ قبل التقريب لأعلى
    net_after = base / (1 + r) if r else base
    discount = max(0.0, money(line_sum - net_after))
    taxable = money(line_sum - discount)
    tax = money(taxable * r)
    incl = money(taxable + tax)
    return {"line_amounts": out, "line_total": money(line_sum), "discount": discount, "taxable": taxable, "tax": tax,
            "inclusive": incl, "payable": money(total), "rounding_amt": money(money(total) - incl)}


# ---------------------------------------------------------------------------
# السعودية: XML بالصيغة القانونية (Canonical) مباشرة حتى تطابق البصمة ما تحسبه الهيئة
# ---------------------------------------------------------------------------

def _tax_cat(rate, tag="cac:TaxCategory"):
    return (f'<{tag}><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5305">{"S" if rate else "O"}</cbc:ID>'
            f'<cbc:Percent>{rate:.2f}</cbc:Percent>'
            '<cac:TaxScheme><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5153">VAT</cbc:ID></cac:TaxScheme>'
            f'</{tag}>')


def _zatca_pure(doc, icv, pih, uid, cur="SAR"):
    """الفاتورة بدون التوقيع وبدون QR (هي ما تُحسب بصمته)"""
    s = seller()
    ts = doc["issued"] or db.now()
    date_, time_ = ts[:10], (ts[11:19] if len(ts) >= 19 else "00:00:00")
    c = f'currencyID="{cur}"'
    x = [f"<Invoice {NS_ROOT}>",
         "<cbc:ProfileID>reporting:1.0</cbc:ProfileID>",
         f"<cbc:ID>{_x(doc['number'])}</cbc:ID>", f"<cbc:UUID>{uid}</cbc:UUID>",
         f"<cbc:IssueDate>{date_}</cbc:IssueDate>", f"<cbc:IssueTime>{time_}</cbc:IssueTime>",
         f'<cbc:InvoiceTypeCode name="0200000">{doc["type_code"]}</cbc:InvoiceTypeCode>',
         f"<cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>", f"<cbc:TaxCurrencyCode>{cur}</cbc:TaxCurrencyCode>"]
    if doc["billing_ref"]:
        b = doc["billing_ref"]
        x.append(f"<cac:BillingReference><cac:InvoiceDocumentReference><cbc:ID>{_x(b['number'])}</cbc:ID>"
                 "</cac:InvoiceDocumentReference></cac:BillingReference>")
    x += [f"<cac:AdditionalDocumentReference><cbc:ID>ICV</cbc:ID><cbc:UUID>{icv}</cbc:UUID></cac:AdditionalDocumentReference>",
          "<cac:AdditionalDocumentReference><cbc:ID>PIH</cbc:ID><cac:Attachment>"
          f'<cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">{pih}</cbc:EmbeddedDocumentBinaryObject>'
          "</cac:Attachment></cac:AdditionalDocumentReference>",
          "<cac:AccountingSupplierParty><cac:Party>",
          f'<cac:PartyIdentification><cbc:ID schemeID="CRN">{_x(s["crn"])}</cbc:ID></cac:PartyIdentification>',
          f"<cac:PostalAddress><cbc:StreetName>{_x(s['street'])}</cbc:StreetName>"
          f"<cbc:BuildingNumber>{_x(s['building'])}</cbc:BuildingNumber>"
          f"<cbc:CitySubdivisionName>{_x(s['district'])}</cbc:CitySubdivisionName>"
          f"<cbc:CityName>{_x(s['city'])}</cbc:CityName><cbc:PostalZone>{_x(s['postal'])}</cbc:PostalZone>"
          "<cac:Country><cbc:IdentificationCode>SA</cbc:IdentificationCode></cac:Country></cac:PostalAddress>",
          f"<cac:PartyTaxScheme><cbc:CompanyID>{_x(s['vat'])}</cbc:CompanyID>"
          "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>",
          f"<cac:PartyLegalEntity><cbc:RegistrationName>{_x(s['name'])}</cbc:RegistrationName></cac:PartyLegalEntity>",
          "</cac:Party></cac:AccountingSupplierParty>"]
    if doc["customer"]:
        x.append("<cac:AccountingCustomerParty><cac:Party><cac:PartyLegalEntity>"
                 f"<cbc:RegistrationName>{_x(doc['customer'])}</cbc:RegistrationName>"
                 "</cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>")
    else:
        x.append("<cac:AccountingCustomerParty></cac:AccountingCustomerParty>")
    pm = f"<cac:PaymentMeans><cbc:PaymentMeansCode>{doc['payment']}</cbc:PaymentMeansCode>"
    if doc["kind"] != "invoice":
        pm += f"<cbc:InstructionNote>{_x(doc['reason'])}</cbc:InstructionNote>"
    x.append(pm + "</cac:PaymentMeans>")
    rate = doc["rate"]
    if doc["discount"]:
        x.append("<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>"
                 "<cbc:AllowanceChargeReason>discount</cbc:AllowanceChargeReason>"
                 f"<cbc:Amount {c}>{_f2(doc['discount'])}</cbc:Amount>{_tax_cat(rate)}</cac:AllowanceCharge>")
    x += [f"<cac:TaxTotal><cbc:TaxAmount {c}>{_f2(doc['tax'])}</cbc:TaxAmount></cac:TaxTotal>",
          f"<cac:TaxTotal><cbc:TaxAmount {c}>{_f2(doc['tax'])}</cbc:TaxAmount><cac:TaxSubtotal>"
          f"<cbc:TaxableAmount {c}>{_f2(doc['taxable'])}</cbc:TaxableAmount><cbc:TaxAmount {c}>{_f2(doc['tax'])}</cbc:TaxAmount>"
          f"{_tax_cat(rate)}</cac:TaxSubtotal></cac:TaxTotal>",
          f"<cac:LegalMonetaryTotal><cbc:LineExtensionAmount {c}>{_f2(doc['line_total'])}</cbc:LineExtensionAmount>"
          f"<cbc:TaxExclusiveAmount {c}>{_f2(doc['taxable'])}</cbc:TaxExclusiveAmount>"
          f"<cbc:TaxInclusiveAmount {c}>{_f2(doc['inclusive'])}</cbc:TaxInclusiveAmount>"
          f"<cbc:AllowanceTotalAmount {c}>{_f2(doc['discount'])}</cbc:AllowanceTotalAmount>"
          f"<cbc:PrepaidAmount {c}>0.00</cbc:PrepaidAmount>"
          + (f"<cbc:PayableRoundingAmount {c}>{_f2(doc['rounding_amt'])}</cbc:PayableRoundingAmount>"
             if abs(doc["rounding_amt"]) >= 0.005 else "")
          + f"<cbc:PayableAmount {c}>{_f2(doc['payable'])}</cbc:PayableAmount></cac:LegalMonetaryTotal>"]
    for i, (ln, am) in enumerate(zip(doc["lines"], doc["line_amounts"]), 1):
        x.append(f"<cac:InvoiceLine><cbc:ID>{i}</cbc:ID>"
                 f'<cbc:InvoicedQuantity unitCode="PCE">{ln["qty"]:.3f}</cbc:InvoicedQuantity>'
                 f"<cbc:LineExtensionAmount {c}>{_f2(am['ext'])}</cbc:LineExtensionAmount>"
                 f"<cac:TaxTotal><cbc:TaxAmount {c}>{_f2(am['tax'])}</cbc:TaxAmount>"
                 f"<cbc:RoundingAmount {c}>{_f2(am['ext'] + am['tax'])}</cbc:RoundingAmount></cac:TaxTotal>"
                 f"<cac:Item><cbc:Name>{_x(ln['name'])}</cbc:Name>{_tax_cat(rate, 'cac:ClassifiedTaxCategory')}</cac:Item>"
                 f"<cac:Price><cbc:PriceAmount {c}>{_f2(am['price'])}</cbc:PriceAmount></cac:Price></cac:InvoiceLine>")
    x.append("</Invoice>")
    return "".join(x)


def invoice_hash(pure_xml):
    """Base64(SHA-256) للفاتورة القانونية (بدون التوقيع وQR)"""
    return base64.b64encode(hashlib.sha256(pure_xml.encode("utf-8")).digest()).decode()


def strip_for_hash(signed_xml):
    """ما تفعله الهيئة عند التحقق: حذف التوقيع وQR وعنوان XML ثم البصمة"""
    s = signed_xml
    if s.startswith("<?xml"):
        s = s[s.index("?>") + 2:]
    s = s.strip()                                # ما خارج العنصر الجذر لا يدخل في الصيغة القانونية
    for start, end in (("<ext:UBLExtensions>", "</ext:UBLExtensions>"), ("<cac:Signature>", "</cac:Signature>")):
        a = s.find(start)
        if a >= 0:
            s = s[:a] + s[s.index(end, a) + len(end):]
    a = s.find("<cac:AdditionalDocumentReference><cbc:ID>QR</cbc:ID>")
    if a >= 0:
        end = "</cac:AdditionalDocumentReference>"
        s = s[:a] + s[s.index(end, a) + len(end):]
    return s


def _tlv(fields):
    out = b""
    for tag, value in enumerate(fields, start=1):
        b = value if isinstance(value, bytes) else str(value).encode("utf-8")
        if len(b) > 255:
            b = b[:255]
        out += bytes([tag, len(b)]) + b
    return base64.b64encode(out).decode("ascii")


# ----- التوقيع (XAdES كما تعتمده الهيئة) -----

_SP_HASH = '''<xades:SignedProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Id="xadesSignedProperties">
                                    <xades:SignedSignatureProperties>
                                        <xades:SigningTime>{time}</xades:SigningTime>
                                        <xades:SigningCertificate>
                                            <xades:Cert>
                                                <xades:CertDigest>
                                                    <ds:DigestMethod xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                                    <ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{cert_hash}</ds:DigestValue>
                                                </xades:CertDigest>
                                                <xades:IssuerSerial>
                                                    <ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{issuer}</ds:X509IssuerName>
                                                    <ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{serial}</ds:X509SerialNumber>
                                                </xades:IssuerSerial>
                                            </xades:Cert>
                                        </xades:SigningCertificate>
                                    </xades:SignedSignatureProperties>
                                </xades:SignedProperties>'''

_SP_EMBED = _SP_HASH.replace(' xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', "").replace(
    ' xmlns:xades="http://uri.etsi.org/01903/v1.3.2#"', "")

_EXT = '''<ext:UBLExtensions>
    <ext:UBLExtension>
        <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
        <ext:ExtensionContent>
            <sig:UBLDocumentSignatures xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2" xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">
                <sac:SignatureInformation>
                    <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
                    <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
                    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature">
                        <ds:SignedInfo>
                            <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                            <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
                            <ds:Reference Id="invoiceSignedData" URI="">
                                <ds:Transforms>
                                    <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                        <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
                                    </ds:Transform>
                                    <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                        <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
                                    </ds:Transform>
                                    <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                        <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath>
                                    </ds:Transform>
                                    <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                                </ds:Transforms>
                                <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                <ds:DigestValue>{invoice_hash}</ds:DigestValue>
                            </ds:Reference>
                            <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
                                <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                <ds:DigestValue>{sp_hash}</ds:DigestValue>
                            </ds:Reference>
                        </ds:SignedInfo>
                        <ds:SignatureValue>{signature}</ds:SignatureValue>
                        <ds:KeyInfo>
                            <ds:X509Data>
                                <ds:X509Certificate>{certificate}</ds:X509Certificate>
                            </ds:X509Data>
                        </ds:KeyInfo>
                        <ds:Object>
                            <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">
                                {signed_properties}
                            </xades:QualifyingProperties>
                        </ds:Object>
                    </ds:Signature>
                </sac:SignatureInformation>
            </sig:UBLDocumentSignatures>
        </ext:ExtensionContent>
    </ext:UBLExtension>
</ext:UBLExtensions>'''


def _hex_b64(data):
    return base64.b64encode(hashlib.sha256(data).hexdigest().encode()).decode()


def _load_cert(cert_b64):
    from cryptography import x509
    return x509.load_der_x509_certificate(base64.b64decode(cert_b64))


def _load_key(pem):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem.encode(), password=None)


def sign_xml(pure_xml, inv_hash, key_pem, cert_b64, qr_fields, signing_time=None):
    """يرجع (XML موقّعاً، توقيع Base64، QR Base64)"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key, cert = _load_key(key_pem), _load_cert(cert_b64)
    signature = base64.b64encode(key.sign(base64.b64decode(inv_hash), ec.ECDSA(hashes.SHA256()))).decode()
    issuer = ", ".join(cert.issuer.rfc4514_string().split(","))
    sp = dict(time=signing_time or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), cert_hash=_hex_b64(cert_b64.encode()),
              issuer=_x(issuer), serial=cert.serial_number)
    sp_hash = _hex_b64(_SP_HASH.format(**sp).encode("utf-8"))
    pub = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    qr = _tlv(list(qr_fields) + [inv_hash, signature, pub, cert.signature])
    ext = _EXT.format(invoice_hash=inv_hash, sp_hash=sp_hash, signature=signature, certificate=cert_b64,
                      signed_properties=_SP_EMBED.format(**sp))
    head_end = pure_xml.index(">") + 1
    anchor = "</cac:AdditionalDocumentReference><cac:AccountingSupplierParty>"
    cut = pure_xml.index(anchor) + len("</cac:AdditionalDocumentReference>")
    qr_ref = ("<cac:AdditionalDocumentReference><cbc:ID>QR</cbc:ID><cac:Attachment>"
              f'<cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">{qr}</cbc:EmbeddedDocumentBinaryObject>'
              "</cac:Attachment></cac:AdditionalDocumentReference>"
              "<cac:Signature><cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>"
              "<cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>"
              "</cac:Signature>")
    signed = ('<?xml version="1.0" encoding="UTF-8"?>\n' + pure_xml[:head_end] + ext + pure_xml[head_end:cut] + qr_ref
              + pure_xml[cut:])
    return signed, signature, qr


def _qr_fields(doc):
    s = seller()
    ts = (doc["issued"] or db.now())[:19].replace(" ", "T")
    return [s["name"], s["vat"], ts, _f2(doc["inclusive"]), _f2(doc["tax"])]


def _signing_material():
    """(المفتاح، الشهادة) للتوقيع: شهادة الإنتاج إن وُجدت"""
    z = _secrets().get("zatca", {})
    if zatca_stage() == "ready":
        return z.get("key"), z["production"]["cert"]
    return None, None


# ----- طلب الشهادة (CSR) والربط -----

def generate_csr(common_name=None, serial=None):
    """مفتاح ECDSA secp256k1 جديد وطلب شهادة بمواصفات الهيئة. يرجع (المفتاح PEM، CSR PEM)"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID, ObjectIdentifier
    from core import vendor
    s = seller()
    env = settings.get("einv_env") or "sandbox"
    template = ZATCA_ENVS.get(env, ZATCA_ENVS["sandbox"])[2].encode()
    key = ec.generate_private_key(ec.SECP256K1())
    serial = serial or f"1-ShopPOS|2-{vendor.VERSION}|3-{_uuid.uuid4()}"
    subject = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
                         x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, (s["branch"] or s["name"])[:60]),
                         x509.NameAttribute(NameOID.ORGANIZATION_NAME, s["name"][:60]),
                         x509.NameAttribute(NameOID.COMMON_NAME, (common_name or f"EGS-{s['vat'][-6:]}")[:60])])
    san = x509.SubjectAlternativeName([x509.DirectoryName(x509.Name([
        x509.NameAttribute(NameOID.SURNAME, serial),
        x509.NameAttribute(NameOID.USER_ID, s["vat"]),
        x509.NameAttribute(NameOID.TITLE, "0100"),                       # فواتير مبسطة
        x509.NameAttribute(ObjectIdentifier("2.5.4.26"), f"{s['building']} {s['street']}, {s['city']}"[:100]),
        x509.NameAttribute(NameOID.BUSINESS_CATEGORY, s["industry"][:60])]))])
    tmpl = x509.UnrecognizedExtension(ObjectIdentifier("1.3.6.1.4.1.311.20.2"), bytes([0x13, len(template)]) + template)
    csr = (x509.CertificateSigningRequestBuilder().subject_name(subject).add_extension(tmpl, critical=False)
           .add_extension(san, critical=False).sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return key_pem, csr.public_bytes(serialization.Encoding.PEM).decode()


def _http(url, body, headers, timeout=20):
    """POST JSON. يرجع (رمز الحالة، dict)"""
    if not url.startswith("https://"):
        raise EInvoiceError("رابط غير آمن")
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(2_000_000)
            code = r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(2_000_000), e.code
    try:
        return code, json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return code, {"message": raw[:300].decode("utf-8", "replace")}


def _zatca_url(path):
    return ZATCA_ENVS.get(settings.get("einv_env") or "sandbox", ZATCA_ENVS["sandbox"])[1] + path


def _basic(token, secret):
    return "Basic " + base64.b64encode(f"{token}:{secret}".encode()).decode()


def _zatca_headers(extra=None):
    return {"Accept-Version": "V2", "Accept-Language": "ar", **(extra or {})}


def _messages(resp):
    v = resp.get("validationResults") or {}
    errs = [f"{m.get('code', '')}: {m.get('message', '')}" for m in v.get("errorMessages") or []]
    warns = [f"{m.get('code', '')}: {m.get('message', '')}" for m in v.get("warningMessages") or []]
    if not errs and not v and resp.get("message"):
        errs = [str(resp.get("message"))]
    for e in resp.get("errors") or []:
        errs.append(str(e.get("message", e)) if isinstance(e, dict) else str(e))
    return errs, warns


def _sample_doc(kind):
    """مستند تجريبي لفحوص الامتثال (فاتورة، إشعار دائن، إشعار مدين)"""
    rate = settings.get_float("vat_rate", 15)
    lines = [{"name": "صنف تجريبي", "qty": 2.0, "price": 10.0}]
    doc = {"kind": kind, "type_code": {"invoice": "388", "credit": "381", "debit": "383"}[kind],
           "number": f"TEST-{kind.upper()}-1", "issued": db.now(), "total": money(20 * (1 + rate / 100)), "rounding": 0,
           "payment": "10", "customer": "", "lines": lines, "rate": rate, "reason": "تصحيح فاتورة",
           "billing_ref": None if kind == "invoice" else {"number": "TEST-INVOICE-1", "date": db.today(), "uuid": "", "total": 0}}
    doc.update(_amounts(lines, doc["total"], 0, rate, False))
    return doc


def zatca_onboard(otp, progress=None):
    """الربط الكامل: CSR + OTP ← شهادة الامتثال ← فحوص الامتثال ← شهادة الإنتاج. يرجع نص النتيجة"""
    def step(t):
        if progress:
            progress(t)
    miss = check_setup(ZATCA)
    if miss:
        raise EInvoiceError("أكمل بيانات المنشأة أولاً:\n• " + "\n• ".join(miss))
    otp = "".join(ch for ch in str(otp or "") if ch.isdigit())
    if not otp:
        raise EInvoiceError("اكتب رمز OTP من بوابة «فاتورة»")
    step("إنشاء مفتاح التوقيع وطلب الشهادة…")
    key_pem, csr_pem = generate_csr()
    step("طلب شهادة الامتثال من الهيئة…")
    code, resp = _http(_zatca_url("/compliance"), {"csr": base64.b64encode(csr_pem.encode()).decode()},
                       _zatca_headers({"OTP": otp}))
    if code != 200 or not resp.get("binarySecurityToken"):
        raise EInvoiceError("رفضت الهيئة طلب الشهادة:\n" + "\n".join(_messages(resp)[0] or [str(resp)[:300]]))
    comp = {"token": resp["binarySecurityToken"], "secret": resp["secret"], "request_id": str(resp.get("requestID")),
            "cert": base64.b64decode(resp["binarySecurityToken"]).decode()}
    d = _secrets()
    d["zatca"] = {"env": settings.get("einv_env") or "sandbox", "key": key_pem, "compliance": comp}
    _save_secrets(d)
    auth = _basic(comp["token"], comp["secret"])
    pih, report = INITIAL_PIH, []
    for i, kind in enumerate(("invoice", "credit", "debit"), 1):
        step(f"فحص الامتثال {i}/3…")
        doc = _sample_doc(kind)
        uid = str(_uuid.uuid4())
        pure = _zatca_pure(doc, i, pih, uid)
        h = invoice_hash(pure)
        signed, _sig, _qr = sign_xml(pure, h, key_pem, comp["cert"], _qr_fields(doc))
        code, resp = _http(_zatca_url("/compliance/invoices"),
                           {"invoiceHash": h, "uuid": uid, "invoice": base64.b64encode(signed.encode()).decode()},
                           _zatca_headers({"Authorization": auth}))
        errs, warns = _messages(resp)
        if code not in (200, 202) or errs:
            raise EInvoiceError(f"لم يجتز المستند التجريبي ({kind}) فحص الهيئة:\n" + "\n".join(errs or [str(resp)[:300]]))
        report += warns
        pih = h
    step("طلب شهادة الإنتاج…")
    code, resp = _http(_zatca_url("/production/csids"), {"compliance_request_id": comp["request_id"]},
                       _zatca_headers({"Authorization": auth}))
    if code != 200 or not resp.get("binarySecurityToken"):
        raise EInvoiceError("تعذر الحصول على شهادة الإنتاج:\n" + "\n".join(_messages(resp)[0] or [str(resp)[:300]]))
    d = _secrets()
    d["zatca"]["production"] = {"token": resp["binarySecurityToken"], "secret": resp["secret"],
                                "cert": base64.b64decode(resp["binarySecurityToken"]).decode()}
    _save_secrets(d)
    from core import audit
    audit.log("ربط الفوترة الإلكترونية", f"تم ربط الجهاز مع منصة فاتورة ({d['zatca']['env']})")
    _resign_pending()
    return "تم الربط بنجاح. الفواتير تُوقَّع وتُرسل للهيئة تلقائياً." + (
        f"\nتنبيهات من فحوص الامتثال: {len(report)}" if report else "")


def _resign_pending():
    """فواتير جُهّزت قبل اكتمال الربط: توقَّع الآن (البصمة والسلسلة لا تتغير)"""
    key, cert = _signing_material()
    if not key:
        return
    for r in db.query("SELECT * FROM einvoices WHERE system=? AND signed=0 AND status IN ('pending','error')", (ZATCA,)):
        info = json.loads(r["info"] or "{}")
        try:
            pure = zlib.decompress(r["xml"]).decode()
            signed, _sig, qr = sign_xml(pure, r["hash"], key, cert, info.get("qr_fields") or [])
            with db.tx() as c:
                c.execute("UPDATE einvoices SET xml=?, qr=?, signed=1 WHERE id=?", (zlib.compress(signed.encode()), qr, r["id"]))
        except Exception as e:  # noqa: BLE001
            with db.tx() as c:
                c.execute("UPDATE einvoices SET status='error', message=? WHERE id=?", (str(e)[:500], r["id"]))


# ---------------------------------------------------------------------------
# الأردن: JoFotara
# ---------------------------------------------------------------------------

JO_CUR = "JO"            # كما في نماذج المنظومة الرسمية (رمز عملة المبالغ)


def _jo_type_name(doc):
    kind = settings.get("jof_kind") or "sales"
    pay = "2" if doc["credit_sale"] else "1"
    return "0" + pay + ("1" if kind == "income" else "2")


def _jofotara_xml(doc, icv, uid):
    s = seller()
    c = f'currencyID="{JO_CUR}"'
    income = (settings.get("jof_kind") or "sales") == "income"
    rate = 0.0 if income else doc["rate"]
    cat = "O" if income or not rate else "S"
    # الخصم يوزَّع على الأسطر بنسبة قيمتها
    share = doc["discount"] / doc["line_total"] if doc["line_total"] else 0
    lines_xml, excl, disc_total, tax_total = [], 0.0, 0.0, 0.0
    for i, (ln, am) in enumerate(zip(doc["lines"], doc["line_amounts"]), 1):
        gross = money(ln["qty"] * am["price"])
        d = money(gross * share)
        net = money(gross - d)
        t = money(net * rate / 100)
        excl += gross
        disc_total += d
        tax_total += t
        lines_xml.append(
            f"<cac:InvoiceLine><cbc:ID>{i}</cbc:ID>"
            f'<cbc:InvoicedQuantity unitCode="PCE">{ln["qty"]:.3f}</cbc:InvoicedQuantity>'
            f"<cbc:LineExtensionAmount {c}>{_f2(net)}</cbc:LineExtensionAmount>"
            f"<cac:TaxTotal><cbc:TaxAmount {c}>{_f2(t)}</cbc:TaxAmount><cbc:RoundingAmount {c}>{_f2(net + t)}</cbc:RoundingAmount>"
            f"<cac:TaxSubtotal><cbc:TaxableAmount {c}>{_f2(net)}</cbc:TaxableAmount><cbc:TaxAmount {c}>{_f2(t)}</cbc:TaxAmount>"
            f'<cac:TaxCategory><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5305">{cat}</cbc:ID><cbc:Percent>{rate:g}</cbc:Percent>'
            '<cac:TaxScheme><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5153">VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>'
            "</cac:TaxSubtotal></cac:TaxTotal>"
            f"<cac:Item><cbc:Name>{_x(ln['name'])}</cbc:Name></cac:Item>"
            f"<cac:Price><cbc:PriceAmount {c}>{_f2(am['price'])}</cbc:PriceAmount>"
            "<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>"
            f"<cbc:AllowanceChargeReason>DISCOUNT</cbc:AllowanceChargeReason><cbc:Amount {c}>{_f2(d)}</cbc:Amount>"
            "</cac:AllowanceCharge></cac:Price></cac:InvoiceLine>")
    if doc["rounding"]:                                    # فرق التقريب لأعلى: سطر بلا ضريبة
        r_ = money(doc["rounding"])
        excl += r_
        lines_xml.append(
            f'<cac:InvoiceLine><cbc:ID>{len(lines_xml) + 1}</cbc:ID><cbc:InvoicedQuantity unitCode="PCE">1.000</cbc:InvoicedQuantity>'
            f"<cbc:LineExtensionAmount {c}>{_f2(r_)}</cbc:LineExtensionAmount>"
            f"<cac:TaxTotal><cbc:TaxAmount {c}>0.00</cbc:TaxAmount><cbc:RoundingAmount {c}>{_f2(r_)}</cbc:RoundingAmount>"
            f"<cac:TaxSubtotal><cbc:TaxableAmount {c}>{_f2(r_)}</cbc:TaxableAmount><cbc:TaxAmount {c}>0.00</cbc:TaxAmount>"
            '<cac:TaxCategory><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5305">Z</cbc:ID><cbc:Percent>0</cbc:Percent>'
            '<cac:TaxScheme><cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5153">VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>'
            "</cac:TaxSubtotal></cac:TaxTotal><cac:Item><cbc:Name>فرق تقريب المبلغ</cbc:Name></cac:Item>"
            f"<cac:Price><cbc:PriceAmount {c}>{_f2(r_)}</cbc:PriceAmount>"
            "<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>"
            f"<cbc:AllowanceChargeReason>DISCOUNT</cbc:AllowanceChargeReason><cbc:Amount {c}>0.00</cbc:Amount>"
            "</cac:AllowanceCharge></cac:Price></cac:InvoiceLine>")
    excl, disc_total, tax_total = money(excl), money(disc_total), money(tax_total)
    incl = money(excl - disc_total + tax_total)
    ts = doc["issued"] or db.now()
    x = [f"<Invoice {NS_ROOT}>", "<cbc:ProfileID>reporting:1.0</cbc:ProfileID>", f"<cbc:ID>{_x(doc['number'])}</cbc:ID>",
         f"<cbc:UUID>{uid}</cbc:UUID>", f"<cbc:IssueDate>{ts[8:10]}-{ts[5:7]}-{ts[:4]}</cbc:IssueDate>",
         f'<cbc:InvoiceTypeCode name="{_jo_type_name(doc)}">{doc["type_code"]}</cbc:InvoiceTypeCode>',
         f"<cbc:Note>{_x(settings.get('shop_name'))}</cbc:Note>",
         "<cbc:DocumentCurrencyCode>JOD</cbc:DocumentCurrencyCode><cbc:TaxCurrencyCode>JOD</cbc:TaxCurrencyCode>"]
    if doc["billing_ref"]:
        b = doc["billing_ref"]
        x.append(f"<cac:BillingReference><cac:InvoiceDocumentReference><cbc:ID>{_x(b['number'])}</cbc:ID>"
                 f"<cbc:UUID>{_x(b['uuid'])}</cbc:UUID><cbc:DocumentDescription>{_f2(b['total'])}</cbc:DocumentDescription>"
                 "</cac:InvoiceDocumentReference></cac:BillingReference>")
    x += [f"<cac:AdditionalDocumentReference><cbc:ID>ICV</cbc:ID><cbc:UUID>{icv}</cbc:UUID></cac:AdditionalDocumentReference>",
          "<cac:AccountingSupplierParty><cac:Party><cac:PostalAddress><cac:Country><cbc:IdentificationCode>JO</cbc:IdentificationCode>"
          f"</cac:Country></cac:PostalAddress><cac:PartyTaxScheme><cbc:CompanyID>{_x(s['vat'])}</cbc:CompanyID>"
          "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
          f"<cac:PartyLegalEntity><cbc:RegistrationName>{_x(s['name'])}</cbc:RegistrationName></cac:PartyLegalEntity>"
          "</cac:Party></cac:AccountingSupplierParty>",
          "<cac:AccountingCustomerParty><cac:Party><cac:PostalAddress><cac:Country><cbc:IdentificationCode>JO</cbc:IdentificationCode>"
          "</cac:Country></cac:PostalAddress><cac:PartyTaxScheme><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
          f"<cac:PartyLegalEntity><cbc:RegistrationName>{_x(doc['customer'] or 'زبون نقدي')}</cbc:RegistrationName>"
          "</cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>",
          f"<cac:SellerSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID>{_x(s['source'])}</cbc:ID>"
          "</cac:PartyIdentification></cac:Party></cac:SellerSupplierParty>"]
    if doc["kind"] != "invoice":
        x.append('<cac:PaymentMeans><cbc:PaymentMeansCode listID="UN/ECE 4461">10</cbc:PaymentMeansCode>'
                 f"<cbc:InstructionNote>{_x(doc['reason'])}</cbc:InstructionNote></cac:PaymentMeans>")
    x += ["<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator><cbc:AllowanceChargeReason>discount"
          f"</cbc:AllowanceChargeReason><cbc:Amount {c}>{_f2(disc_total)}</cbc:Amount></cac:AllowanceCharge>"]
    if not income:
        x.append(f"<cac:TaxTotal><cbc:TaxAmount {c}>{_f2(tax_total)}</cbc:TaxAmount></cac:TaxTotal>")
    x.append(f"<cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount {c}>{_f2(excl)}</cbc:TaxExclusiveAmount>"
             f"<cbc:TaxInclusiveAmount {c}>{_f2(incl)}</cbc:TaxInclusiveAmount>"
             f"<cbc:AllowanceTotalAmount {c}>{_f2(disc_total)}</cbc:AllowanceTotalAmount>"
             f"<cbc:PayableAmount {c}>{_f2(incl)}</cbc:PayableAmount></cac:LegalMonetaryTotal>")
    x += lines_xml
    x.append("</Invoice>")
    return '<?xml version="1.0" encoding="UTF-8"?>' + "".join(x)


# ---------------------------------------------------------------------------
# التسجيل لحظة البيع/المرتجع، والإرسال
# ---------------------------------------------------------------------------

def register(kind, ref_id):
    """يُستدعى بعد حفظ الفاتورة أو المرتجع. لا يرفع خطأ أبداً"""
    sys_ = system()
    if not sys_:
        return None
    col = "invoice_id" if kind == "invoice" else "return_id"
    try:
        with _LOCK:
            if db.query_one(f"SELECT id FROM einvoices WHERE system=? AND doc_type=? AND {col}=?", (sys_, kind, ref_id)):
                return None
            doc = _document(kind, ref_id)
            uid = str(_uuid.uuid4())
            icv = int(db.get_meta(f"einv_icv_{sys_}") or 0) + 1
            info = {}
            if sys_ == ZATCA:
                pih = db.get_meta("einv_pih") or INITIAL_PIH
                pure = _zatca_pure(doc, icv, pih, uid)
                h = invoice_hash(pure)
                info["qr_fields"] = _qr_fields(doc)
                key, cert = _signing_material()
                xml, signed, qr = pure, 0, None
                if key:
                    xml, _sig, qr = sign_xml(pure, h, key, cert, info["qr_fields"])
                    signed = 1
            else:
                pih, h, qr = "", "", None
                xml, signed = _jofotara_xml(doc, icv, uid), 1
            with db.tx() as c:
                c.execute("""INSERT INTO einvoices(system, doc_type, invoice_id, return_id, number, uuid, icv, pih, hash, xml,
                                                   qr, signed, status, info, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                          (sys_, kind, doc["invoice_id"] if kind == "invoice" else None, doc["return_id"], doc["number"], uid,
                           icv, pih, h, zlib.compress(xml.encode("utf-8")), qr, signed, json.dumps(info, ensure_ascii=False),
                           db.now()))
                c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (f"einv_icv_{sys_}", str(icv)))
                if sys_ == ZATCA:
                    c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('einv_pih', ?)", (h,))
            return uid
    except Exception as e:  # noqa: BLE001 — البيع تمّ؛ الخطأ يظهر في شاشة الفوترة وفي التدقيق
        try:
            with db.tx() as c:
                c.execute("""INSERT INTO einvoices(system, doc_type, invoice_id, return_id, number, status, message, created_at)
                             VALUES (?, ?, ?, ?, ?, 'error', ?, ?)""",
                          (sys_, kind, ref_id if kind == "invoice" else None, ref_id if kind != "invoice" else None,
                           str(ref_id), str(e)[:500], db.now()))
        except Exception:  # noqa: BLE001
            pass
        return None


def _send_one(r, timeout=20):
    sys_ = r["system"]
    xml = zlib.decompress(r["xml"]).decode("utf-8")
    b64 = base64.b64encode(xml.encode("utf-8")).decode()
    if sys_ == ZATCA:
        if not r["signed"]:
            return "pending", "بانتظار ربط الجهاز مع منصة فاتورة", None
        p = _secrets()["zatca"]["production"]
        code, resp = _http(_zatca_url("/invoices/reporting/single"), {"invoiceHash": r["hash"], "uuid": r["uuid"], "invoice": b64},
                           _zatca_headers({"Authorization": _basic(p["token"], p["secret"]), "Clearance-Status": "0"}), timeout)
        errs, warns = _messages(resp)
        if code in (200, 202) and not errs:
            return ("warning" if warns else "reported"), "\n".join(warns), None
        if code in (400, 409):
            return "rejected", "\n".join(errs or [str(resp)[:400]]), None
        return "pending", f"HTTP {code}: " + "\n".join(errs or [str(resp)[:200]]), None
    secret = _secrets().get("jof_secret", "")
    code, resp = _http(JOFOTARA_URL, {"invoice": b64}, {"Client-Id": settings.get("jof_client_id") or "", "Secret-Key": secret}, timeout)
    res = resp.get("EINV_RESULTS") or {}
    errs = [f"{e.get('EINV_CODE', '')}: {e.get('EINV_MESSAGE', '')}" for e in res.get("ERRORS") or []]
    warns = [f"{e.get('EINV_CODE', '')}: {e.get('EINV_MESSAGE', '')}" for e in res.get("WARNINGS") or []]
    if code == 200 and str(resp.get("EINV_STATUS", "")).upper() in ("SUBMITTED", "ALREADY_SUBMITTED") and not errs:
        return ("warning" if warns else "reported"), "\n".join(warns), resp.get("EINV_QR")
    if code in (400, 409) or errs:
        return "rejected", "\n".join(errs or [str(resp)[:400]]), None
    return "pending", f"HTTP {code}: {str(resp)[:200]}", None


def send_pending(limit=25):
    """إرسال ما لم يُرسل بعد (يُستدعى في الخلفية). يرجع عدد ما أُرسل بنجاح"""
    if not enabled() or not _SEND_LOCK.acquire(blocking=False):
        return 0
    ok = 0
    try:
        rows = db.query("""SELECT * FROM einvoices WHERE system=? AND status='pending' AND xml IS NOT NULL
                           ORDER BY icv LIMIT ?""", (system(), limit))
        for r in rows:
            try:
                status, msg, qr = _send_one(r)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                status, msg, qr = "pending", f"لا اتصال: {e}", None
                with db.tx() as c:
                    c.execute("UPDATE einvoices SET attempts = attempts + 1, message=? WHERE id=?", (msg[:500], r["id"]))
                break                                  # لا إنترنت: نحاول لاحقاً
            _store_result(r, status, msg, qr)
            if status in ("reported", "warning"):
                ok += 1
            elif status == "pending":
                break
    finally:
        _SEND_LOCK.release()
    return ok


def _store_result(r, status, msg, qr):
    with db.tx() as c:
        c.execute("""UPDATE einvoices SET status=?, message=?, attempts = attempts + 1,
                     sent_at = CASE WHEN ? IN ('reported','warning') THEN ? ELSE sent_at END,
                     qr = COALESCE(?, qr) WHERE id=?""", (status, (msg or "")[:2000], status, db.now(), qr, r["id"]))


def quick_send(invoice_id, timeout=5):
    """JoFotara: إرسال فوري قبل طباعة الإيصال ليُطبع رمز QR الرسمي (بحد أقصى ثوانٍ قليلة)"""
    if system() != JOFOTARA or not _SEND_LOCK.acquire(blocking=False):
        return False
    try:
        r = db.query_one("""SELECT * FROM einvoices WHERE system=? AND doc_type='invoice' AND invoice_id=?
                            AND status='pending' AND xml IS NOT NULL""", (JOFOTARA, invoice_id))
        if not r:
            return False
        try:
            status, msg, qr = _send_one(r, timeout)
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
        _store_result(r, status, msg, qr)
        return bool(qr)
    finally:
        _SEND_LOCK.release()


def retry(einv_id):
    """إعادة مستند مرفوض أو متعثر إلى طابور الإرسال"""
    with db.tx() as c:
        c.execute("UPDATE einvoices SET status='pending' WHERE id=? AND status IN ('rejected','error')", (einv_id,))


# ---------------------------------------------------------------------------
# للعرض والطباعة
# ---------------------------------------------------------------------------

def for_invoice(invoice_id):
    if not enabled():
        return None
    return db.query_one("SELECT * FROM einvoices WHERE system=? AND doc_type='invoice' AND invoice_id=?", (system(), invoice_id))


def receipt_qr_text(invoice_id):
    """نص QR للفاتورة على الإيصال (أو None فيُستخدم QR المرحلة الأولى)"""
    r = for_invoice(invoice_id)
    return r["qr"] if r and r["qr"] else None


def summary():
    rows = db.query("SELECT status, COUNT(*) AS n FROM einvoices WHERE system=? GROUP BY status", (system(),))
    out = {k: 0 for k in STATUS}
    out.update({r["status"]: r["n"] for r in rows})
    late = db.scalar("""SELECT COUNT(*) FROM einvoices WHERE system=? AND status IN ('pending','error')
                        AND created_at < datetime('now', 'localtime', '-24 hours')""", (system(),)) or 0
    out["late"] = late
    return out


def recent(limit=200, status=None):
    sql = "SELECT id, doc_type, number, icv, status, message, created_at, sent_at, attempts FROM einvoices WHERE system=?"
    params = [system()]
    if status:
        sql += " AND status=?"
        params.append(status)
    return db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))


def xml_of(einv_id):
    r = db.query_one("SELECT xml FROM einvoices WHERE id=?", (einv_id,))
    return zlib.decompress(r["xml"]).decode("utf-8") if r and r["xml"] else ""

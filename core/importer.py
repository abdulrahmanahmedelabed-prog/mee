# -*- coding: utf-8 -*-
"""
نقل الدفتر القديم: استيراد العملاء والموردين وديونهم من ملف Excel محفوظ بصيغة CSV.
الأعمدة (السطر الأول عناوين):
  العملاء:  الاسم، الهاتف، العنوان، الدين الحالي، حد الدين
  الموردون: الاسم، الهاتف، العنوان، المستحق له
من له نفس الهاتف (أو نفس الاسم بدون هاتف) لا يُكرَّر.
"""

import csv

from core import customers, suppliers
from core.utils import to_float

CUSTOMER_HEADERS = ["الاسم", "الهاتف", "العنوان", "الدين الحالي", "حد الدين"]
SUPPLIER_HEADERS = ["الاسم", "الهاتف", "العنوان", "المستحق له"]


def _rows(path, width):
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.reader(f, delimiter=delim)
        next(reader, None)
        for i, row in enumerate(reader, start=2):
            if row and any(c.strip() for c in row):
                yield i, [c.strip() for c in (row + [""] * width)[:width]]


def write_template(path, kind):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(CUSTOMER_HEADERS if kind == "customers" else SUPPLIER_HEADERS)


def _existing(rows):
    phones = {"".join(ch for ch in (r["phone"] or "") if ch.isdigit()) for r in rows} - {""}
    names = {r["name"].strip() for r in rows}
    return phones, names


def import_customers(path):
    phones, names = _existing(customers.list_customers())
    added, skipped, errors = 0, 0, []
    for i, (name, phone, address, debt, limit) in _rows(path, 5):
        key = "".join(ch for ch in phone if ch.isdigit())
        if (key and key in phones) or (not key and name in names):
            skipped += 1
            continue
        try:
            customers.add_customer(name, phone, address, to_float(limit, 0), "مستورد من الدفتر", to_float(debt, 0))
            added += 1
            phones.add(key)
            names.add(name)
        except (ValueError, TypeError) as e:
            errors.append(f"سطر {i}: {e}")
    return added, skipped, errors


def import_suppliers(path):
    phones, names = _existing(suppliers.list_suppliers())
    added, skipped, errors = 0, 0, []
    for i, (name, phone, address, due) in _rows(path, 4):
        key = "".join(ch for ch in phone if ch.isdigit())
        if (key and key in phones) or (not key and name in names):
            skipped += 1
            continue
        try:
            suppliers.add_supplier(name, phone, address, "مستورد من الدفتر", to_float(due, 0))
            added += 1
            phones.add(key)
            names.add(name)
        except (ValueError, TypeError) as e:
            errors.append(f"سطر {i}: {e}")
    return added, skipped, errors

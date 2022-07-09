#!/usr/bin/env python

import decimal
import json
import logging
import os
import re
import shutil
from urllib import request, parse
from collections import OrderedDict

ROOT_DIR = os.path.join(os.path.dirname(__file__), os.path.pardir)

main_pool_uuids = {
  "base": {
    "resistors": {
      "0402": "44fe0594-19d5-403e-9ae8-7c4c59c3668f",
      "0603": "cbeda48c-7fb0-4cfb-a4de-d9672e8cc190",
      "0805": "0aaa5955-e860-49fa-9b04-c3fe2d4bc010",
      "1206": "69d9d487-801a-40ab-a821-5a7a6ee8c623",
    },
    "capacitors": {
      "0402": "29043bfd-c944-47cb-ae49-8dc6e1cf7257",
      "0603": "436da8ee-a0a4-4ab4-ae41-10323bb580e5",
      "0805": "2f50150e-b407-4eda-899c-4a8339af9433",
      "1206": "7537f389-14a5-43a6-9b2a-100266cd51d8",
      "1210": "ce744d78-f7d9-4997-8666-fd10d77eccb6",
    },
  },
}

class UnsupportedListingError(Exception):
  pass

dec_ctx = decimal.Context(prec=100)

def parse_si_prefix(v, suffix=""):
  v = str(v).strip()
  if v.lower() == "n/a":
    return "0"
  v = v.rstrip(suffix + " ")
  prefix = v[-1:]
  if not prefix or prefix.isnumeric():
    exp = 0
  else:
    exp = dict(p=-12, n=-9, u=-6, m=-3, k=3, K=3, M=6, G=9, T=12).get(prefix)
    if not exp:
      raise UnsupportedListingError("unsupported SI prefix '%s'" % prefix)
    v = v[:-1]
  n = dec_ctx.create_decimal(v.strip())
  return format((n * dec_ctx.create_decimal("1e%s" % exp)).normalize(), 'f')

def format_si_prefix(v, suffix=""):
  n = dec_ctx.create_decimal(v)
  if n == 0:
    return ("0 " + suffix).rstrip()
  th = dec_ctx.create_decimal(1e12)
  for prefix in "TGMk munp":
    if n >= th:
      return (format((n / th).normalize(), 'f') + " " + prefix.strip() + suffix).rstrip()
    th /= 1000

def normalize_obj(o):
  if isinstance(o, dict):
    return {k.lower().strip(): normalize_obj(v) for k, v in o.items()}
  if isinstance(o, list):
    return [normalize_obj(i) for i in o]
  return o

def gen_resistor(r):
  package = r["part_attrs"].get("package")
  base_uuid = main_pool_uuids["base"]["resistors"].get(package)
  value = parse_si_prefix(r["part_attrs"]["value"])
  if not base_uuid:
    raise UnsupportedListingError("bad package type %s" % package)
  return OrderedDict(
    MPN=[False, r["mpn"]],
    base=base_uuid,
    datasheet=[False, r["part_datasheet"]],
    description=[False, r["part_desc"]],
    inherit_model=True,
    inherit_tags=True,
    manufacturer=[True, ""],
    parametric=OrderedDict(
      pmax=parse_si_prefix(r["part_attrs"]["power rating"], "W"),
      table="resistors",
      tolerance=parse_si_prefix(r["part_attrs"].get("tolerance", ""), "%"),
      value=value,
    ),
    tags=[],
    type="part",
    uuid=r["id"],
    value=[False, format_si_prefix(value, "Ω")],
  )

def gen_capacitor(c):
  package = c["part_attrs"].get("package")

  base_uuid = main_pool_uuids["base"]["capacitors"].get(package)
  if not base_uuid:
    raise UnsupportedListingError("bad package type %s" % package)

  tolerance = c["part_attrs"]["tolerance"]
  if not re.match(r'^\s*[\d.]+\s*[%]\s*$', tolerance):
    tolerance = ""
  else:
    tolerance = parse_si_prefix(tolerance, "%")

  typ = c["part_attrs"].get("dielectric", "").strip()
  if typ == "C0G (NP0)":
    typ = "C0G/NP0"
  if "electrolytic" in c["part_attrs"]["type"].lower():
    typ = "Electrolytic"

  value = parse_si_prefix(c["part_attrs"]["value"])

  return OrderedDict(
    MPN=[False, c["mpn"]],
    base=base_uuid,
    datasheet=[False, c["part_datasheet"]],
    description=[False, c["part_desc"]],
    inherit_model=True,
    inherit_tags=True,
    manufacturer=[True, ""],
    parametric=OrderedDict(
      table="capacitors",
      tolerance=tolerance,
      type=typ,
      value=value,
      wvdc=parse_si_prefix(c["part_attrs"]["voltage rating"], "V"),
    ),
    tags=[],
    type="part",
    uuid=c["id"],
    value=[False, format_si_prefix(value, "F")],
  )

def sync_capacitors():
  d = parse.urlencode({
    "query": "",
    "house": "1",
    "class": "capacitor",
    "limit": "1000",
  }).encode('utf8')
  req = request.Request(
    "https://factory.macrofab.com/part/search",
    data=d,
    headers={
      "Accept": "application/json",
    },
  )
  with request.urlopen(req) as res:
    listing = normalize_obj(json.load(res))

  rdir = os.path.join(ROOT_DIR, "parts", "capacitor")
  shutil.rmtree(rdir)
  os.mkdir(rdir)

  for c in listing:
    try:
      cgen = gen_capacitor(c)
    except UnsupportedListingError as e:
      logging.warning("part '%s' is not supported: %s", c["mpn"], e)
      continue
    with open(os.path.join(rdir, c["mpn"] + ".json"), 'w') as f:
      json.dump(cgen, f, indent=4, ensure_ascii=False)

def sync_resistors():
  d = parse.urlencode({
    "query": "",
    "house": "1",
    "class": "resistor",
    "limit": "1000",
  }).encode('utf8')
  req = request.Request(
    "https://factory.macrofab.com/part/search",
    data=d,
    headers={
      "Accept": "application/json",
    },
  )
  with request.urlopen(req) as res:
    listing = normalize_obj(json.load(res))

  rdir = os.path.join(ROOT_DIR, "parts", "resistor")
  shutil.rmtree(rdir)
  os.mkdir(rdir)

  for r in listing:
    try:
      rgen = gen_resistor(r)
    except UnsupportedListingError as e:
      logging.warning("part '%s' is not supported: %s", r["mpn"], e)
      continue
    with open(os.path.join(rdir, r["mpn"] + ".json"), 'w') as f:
      json.dump(rgen, f, indent=4, ensure_ascii=False)

def main():
  sync_resistors()
  sync_capacitors()

if __name__ == '__main__':
  main()

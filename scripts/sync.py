#!/usr/bin/env python

import json
import decimal
import logging
import os
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
    manufacturer=[False, ""],
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
  logging.info("syncing resistors")
  sync_resistors()

if __name__ == '__main__':
  main()

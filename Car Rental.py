#!/usr/bin/env python3
"""Car Rental Management System (binary file I/O + struct)
Python 3.10+
- Fixed-length record files with header (cars.dat, customers.dat, rentals.dat)
- pack/unpack using struct (little-endian)
- CRUD menu: Add / Update / Delete (logical) / View
- Generate text report (report.txt) with 3 example tables (Customer-based, Rental-based, Car summary)
- Sample data generator (create >=50 car records, sample customers, sample rentals)
- Uses only Python Standard Library
"""

from __future__ import annotations
import struct
import os
import sys
import time
import datetime
import random
import json
from typing import Tuple, List

# --- Constants & Formats ---
HEADER_SIZE = 256  # bytes reserved at start of each .dat file for a simple JSON-like header (utf-8 padded)
ENDIAN = '<'  # little-endian

# cars.dat format: < i i i i f i 12s 12s 16s i i
CARS_STRUCT_FMT = ENDIAN + 'i i i i f i 12s 12s 16s i i'
CARS_RECORD_SIZE = struct.calcsize(CARS_STRUCT_FMT)

# customers.dat format: < i i 32s 16s 32s i i
# fields: cust_id, status, name(32), phone(16), email(32), created_at, updated_at
CUST_STRUCT_FMT = ENDIAN + 'i i 32s 16s 32s i i'
CUST_RECORD_SIZE = struct.calcsize(CUST_STRUCT_FMT)

# rentals.dat format: < i i i i i f i i
# we'll map fields as:
# rent_id, status, car_id, cust_id, pickup_ts (int), daily_rate (float), days (int), is_returned (int)
RENT_STRUCT_FMT = ENDIAN + 'i i i i i f i i'
RENT_RECORD_SIZE = struct.calcsize(RENT_STRUCT_FMT)

# Filenames
CARS_FILE = 'cars.dat'
CUST_FILE = 'customers.dat'
RENT_FILE = 'rentals.dat'
REPORT_FILE = 'report.txt'

# --- Helpers for fixed-length strings ---
def str_to_fixed_bytes(s: str, length: int) -> bytes:
    b = s.encode('utf-8')
    if len(b) > length:
        return b[:length]
    return b.ljust(length, b'\x00')

def fixed_bytes_to_str(b: bytes) -> str:
    return b.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')

# --- Header management ---
def write_header(filename: str, meta: dict):
    with open(filename, 'r+b') as f:
        raw = json.dumps(meta, ensure_ascii=False).encode('utf-8')
        if len(raw) > HEADER_SIZE:
            raise ValueError('Header too large')
        f.seek(0)
        f.write(raw)
        f.write(b'\x00' * (HEADER_SIZE - len(raw)))
        f.flush(); os.fsync(f.fileno())

def read_header(filename: str) -> dict:
    if not os.path.exists(filename):
        return {}
    with open(filename, 'rb') as f:
        data = f.read(HEADER_SIZE)
        try:
            s = data.split(b'\x00', 1)[0].decode('utf-8')
            if not s:
                return {}
            return json.loads(s)
        except Exception:
            return {}

def ensure_file(filename: str, record_size: int):
    if not os.path.exists(filename):
        with open(filename, 'wb') as f:
            meta = {
                'version': '1.0',
                'record_size': record_size,
                'created_at': int(time.time()),
                'count': 0,
                'next_id': 1001,
                'free_list': []
            }
            raw = json.dumps(meta, ensure_ascii=False).encode('utf-8')
            f.write(raw)
            f.write(b'\x00' * (HEADER_SIZE - len(raw)))
            f.flush(); os.fsync(f.fileno())

# --- Cars pack/unpack ---
def pack_car(car: dict) -> bytes:
    return struct.pack(
        CARS_STRUCT_FMT,
        car['car_id'],
        car['status'],
        car['is_rented'],
        car['year'],
        float(car['daily_rate_thb']),
        car['odometer_km'],
        str_to_fixed_bytes(car.get('license_plate',''), 12),
        str_to_fixed_bytes(car.get('brand',''), 12),
        str_to_fixed_bytes(car.get('model',''), 16),
        car['created_at'],
        car['updated_at']
    )

def unpack_car(raw: bytes) -> dict:
    vals = struct.unpack(CARS_STRUCT_FMT, raw)
    return {
        'car_id': vals[0],
        'status': vals[1],
        'is_rented': vals[2],
        'year': vals[3],
        'daily_rate_thb': float(vals[4]),
        'odometer_km': vals[5],
        'license_plate': fixed_bytes_to_str(vals[6]),
        'brand': fixed_bytes_to_str(vals[7]),
        'model': fixed_bytes_to_str(vals[8]),
        'created_at': vals[9],
        'updated_at': vals[10]
    }

# --- Customers pack/unpack ---
def pack_customer(cust: dict) -> bytes:
    return struct.pack(
        CUST_STRUCT_FMT,
        cust['cust_id'],
        cust['status'],
        str_to_fixed_bytes(cust.get('name',''), 32),
        str_to_fixed_bytes(cust.get('phone',''), 16),
        str_to_fixed_bytes(cust.get('email',''), 32),
        cust['created_at'],
        cust['updated_at']
    )

def unpack_customer(raw: bytes) -> dict:
    vals = struct.unpack(CUST_STRUCT_FMT, raw)
    return {
        'cust_id': vals[0],
        'status': vals[1],
        'name': fixed_bytes_to_str(vals[2]),
        'phone': fixed_bytes_to_str(vals[3]),
        'email': fixed_bytes_to_str(vals[4]),
        'created_at': vals[5],
        'updated_at': vals[6]
    }

# --- Rentals pack/unpack ---
def pack_rental(r: dict) -> bytes:
    return struct.pack(
        RENT_STRUCT_FMT,
        r['rent_id'],
        r['status'],
        r['car_id'],
        r['cust_id'],
        int(r['pickup_ts']),
        float(r['daily_rate']),
        int(r['days']),
        int(r['is_returned'])
    )

def unpack_rental(raw: bytes) -> dict:
    vals = struct.unpack(RENT_STRUCT_FMT, raw)
    return {
        'rent_id': vals[0],
        'status': vals[1],
        'car_id': vals[2],
        'cust_id': vals[3],
        'pickup_ts': vals[4],
        'daily_rate': float(vals[5]),
        'days': vals[6],
        'is_returned': vals[7]
    }

# --- Low-level record access ---
def get_record_offset(index: int, record_size: int) -> int:
    return HEADER_SIZE + index * record_size

def append_record(filename: str, record_bytes: bytes, record_size: int):
    with open(filename, 'r+b') as f:
        meta = read_header(filename)
        count = meta.get('count', 0)
        f.seek(HEADER_SIZE + count * record_size)
        f.write(record_bytes)
        meta['count'] = count + 1
        meta['next_id'] = meta.get('next_id', 1001) + 1
        meta['last_updated'] = int(time.time())
        write_header(filename, meta)

def write_record_at(filename: str, index: int, record_bytes: bytes, record_size: int):
    with open(filename, 'r+b') as f:
        f.seek(get_record_offset(index, record_size))
        f.write(record_bytes)
        meta = read_header(filename)
        meta['last_updated'] = int(time.time())
        write_header(filename, meta)

def read_record_at(filename: str, index: int, record_size: int) -> bytes | None:
    with open(filename, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        offset = get_record_offset(index, record_size)
        if offset + record_size > file_size:
            return None
        f.seek(offset)
        return f.read(record_size)

# --- Find helpers ---
def find_car_index_by_id(car_id: int) -> int | None:
    meta = read_header(CARS_FILE)
    count = meta.get('count', 0)
    for idx in range(count):
        raw = read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE)
        if not raw: break
        car = unpack_car(raw)
        if car['car_id'] == car_id:
            return idx
    return None

def find_customer_index_by_id(cust_id: int) -> int | None:
    meta = read_header(CUST_FILE)
    count = meta.get('count', 0)
    for idx in range(count):
        raw = read_record_at(CUST_FILE, idx, CUST_RECORD_SIZE)
        if not raw: break
        c = unpack_customer(raw)
        if c['cust_id'] == cust_id:
            return idx
    return None

def find_rental_index_by_id(rent_id: int) -> int | None:
    meta = read_header(RENT_FILE)
    count = meta.get('count', 0)
    for idx in range(count):
        raw = read_record_at(RENT_FILE, idx, RENT_RECORD_SIZE)
        if not raw: break
        r = unpack_rental(raw)
        if r['rent_id'] == rent_id:
            return idx
    return None

# --- High-level Cars CRUD (unchanged) ---
def add_car_interactive():
    meta = read_header(CARS_FILE)
    next_id = meta.get('next_id', 1001)
    car = {}
    car['car_id'] = next_id
    car['status'] = 1
    car['is_rented'] = 0
    try:
        car['year'] = int(input('Year (e.g., 2021): ').strip())
    except:
        car['year'] = 2020
    try:
        car['daily_rate_thb'] = float(input('Daily rate (THB): ').strip())
    except:
        car['daily_rate_thb'] = 1000.0
    try:
        car['odometer_km'] = int(input('Odometer (km): ').strip())
    except:
        car['odometer_km'] = 0
    car['license_plate'] = input('License plate: ').strip()
    car['brand'] = input('Brand: ').strip()
    car['model'] = input('Model: ').strip()
    ts = int(time.time())
    car['created_at'] = ts
    car['updated_at'] = ts
    raw = pack_car(car)
    append_record(CARS_FILE, raw, CARS_RECORD_SIZE)
    print(f"Added car_id={car['car_id']}")

def update_car_interactive():
    try:
        cid = int(input('Enter car_id to update: ').strip())
    except:
        print('Invalid id'); return
    idx = find_car_index_by_id(cid)
    if idx is None:
        print('Car not found'); return
    raw = read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE)
    car = unpack_car(raw)
    print('Current:', car)
    s = input(f"Year [{car['year']}]: ").strip()
    if s: car['year'] = int(s)
    s = input(f"Daily rate [{car['daily_rate_thb']}]: ").strip()
    if s: car['daily_rate_thb'] = float(s)
    s = input(f"Odometer [{car['odometer_km']}]: ").strip()
    if s: car['odometer_km'] = int(s)
    s = input(f"License plate [{car['license_plate']}]: ").strip()
    if s: car['license_plate'] = s
    s = input(f"Brand [{car['brand']}]: ").strip()
    if s: car['brand'] = s
    s = input(f"Model [{car['model']}]: ").strip()
    if s: car['model'] = s
    car['updated_at'] = int(time.time())
    raw2 = pack_car(car)
    write_record_at(CARS_FILE, idx, raw2, CARS_RECORD_SIZE)
    print('Updated')

def delete_car_interactive():
    try:
        cid = int(input('Enter car_id to delete (logical): ').strip())
    except:
        print('Invalid id'); return
    idx = find_car_index_by_id(cid)
    if idx is None:
        print('Car not found'); return
    raw = read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE)
    car = unpack_car(raw)
    if car['status'] == 0:
        print('Already deleted'); return
    car['status'] = 0
    car['updated_at'] = int(time.time())
    write_record_at(CARS_FILE, idx, pack_car(car), CARS_RECORD_SIZE)
    print('Deleted (logical)')

def view_all_cars(filter_active: bool | None = None):
    meta = read_header(CARS_FILE)
    count = meta.get('count', 0)
    rows = []
    for idx in range(count):
        raw = read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE)
        if not raw: break
        car = unpack_car(raw)
        if filter_active is True and car['status'] != 1:
            continue
        if filter_active is False and car['status'] != 0:
            continue
        rows.append(car)
    print('+------+------------+-----------+-----------+------+----------+--------+')
    print('| ID   | Plate      | Brand     | Model     | Year | Rate     | Status |')
    print('+------+------------+-----------+-----------+------+----------+--------+')
    for c in rows:
        st = 'Active' if c['status']==1 else 'Deleted'
        print(f"| {c['car_id']:<4} | {c['license_plate'][:10]:<10} | {c['brand'][:9]:<9} | {c['model'][:9]:<9} | {c['year']:<4} | {c['daily_rate_thb']:<8.2f} | {st:<6}|")
    print('+------+------------+-----------+-----------+------+----------+--------+')

def view_one_car():
    try:
        cid = int(input('Enter car_id to view: ').strip())
    except:
        print('Invalid id'); return
    idx = find_car_index_by_id(cid)
    if idx is None:
        print('Not found'); return
    car = unpack_car(read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE))
    print(json.dumps(car, ensure_ascii=False, indent=2))

# --- Customers (simple CRUD-like add/view) ---
def add_customer(name: str, phone: str = '', email: str = '') -> int:
    ensure_file(CUST_FILE, CUST_RECORD_SIZE)
    meta = read_header(CUST_FILE)
    cust_id = meta.get('next_id', 1001)
    ts = int(time.time())
    cust = {
        'cust_id': cust_id,
        'status': 1,
        'name': name,
        'phone': phone,
        'email': email,
        'created_at': ts,
        'updated_at': ts
    }
    append_record(CUST_FILE, pack_customer(cust), CUST_RECORD_SIZE)
    return cust_id

def view_all_customers():
    meta = read_header(CUST_FILE)
    count = meta.get('count', 0)
    rows = []
    for idx in range(count):
        raw = read_record_at(CUST_FILE, idx, CUST_RECORD_SIZE)
        if not raw: break
        rows.append(unpack_customer(raw))
    print('+------+-------------------------------+----------------+--------------------+')
    print('| ID   | Name                          | Phone          | Email              |')
    print('+------+-------------------------------+----------------+--------------------+')
    for c in rows:
        print(f"| {c['cust_id']:<4} | {c['name'][:30]:<30} | {c['phone'][:14]:<14} | {c['email'][:18]:<18} |")
    print('+------+-------------------------------+----------------+--------------------+')

# --- Rentals (create/view) ---
def add_rental(car_id: int, cust_id: int, pickup_dt: datetime.date, days: int, daily_rate: float):
    ensure_file(RENT_FILE, RENT_RECORD_SIZE)
    meta = read_header(RENT_FILE)
    rent_id = meta.get('next_id', 1001)
    pickup_ts = int(time.mktime(pickup_dt.timetuple()))
    rent = {
        'rent_id': rent_id,
        'status': 1,
        'car_id': car_id,
        'cust_id': cust_id,
        'pickup_ts': pickup_ts,
        'daily_rate': float(daily_rate),
        'days': int(days),
        'is_returned': 0
    }
    append_record(RENT_FILE, pack_rental(rent), RENT_RECORD_SIZE)
    # mark car as rented
    idx = find_car_index_by_id(car_id)
    if idx is not None:
        car = unpack_car(read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE))
        car['is_rented'] = 1
        car['updated_at'] = int(time.time())
        write_record_at(CARS_FILE, idx, pack_car(car), CARS_RECORD_SIZE)
    return rent_id

def view_all_rentals():
    meta = read_header(RENT_FILE)
    count = meta.get('count', 0)
    rows = []
    for idx in range(count):
        raw = read_record_at(RENT_FILE, idx, RENT_RECORD_SIZE)
        if not raw: break
        rows.append(unpack_rental(raw))
    print('+------+--------+--------+---------------------+------+---------+')
    print('| Rent | Car ID | CustID | Pick-up (YYYY-MM-DD) | Days | Returned |')
    print('+------+--------+--------+---------------------+------+---------+')
    for r in rows:
        dt = datetime.datetime.fromtimestamp(r['pickup_ts']).strftime('%Y-%m-%d')
        print(f"| {r['rent_id']:<4} | {r['car_id']:<6} | {r['cust_id']:<6} | {dt:<19} | {r['days']:<4} | {r['is_returned']:<7} |")
    print('+------+--------+--------+---------------------+------+---------+')

# --- Report generation (3 example sections) ---
def generate_report_all():
    """Generate report.txt with 3 example tables:
       A) Customer-based rentals
       B) Rental detail list (periods)
       C) Car summary (existing)
    """
    # read data from files
    ensure_file(CARS_FILE, CARS_RECORD_SIZE)
    ensure_file(CUST_FILE, CUST_RECORD_SIZE)
    ensure_file(RENT_FILE, RENT_RECORD_SIZE)

    # load cars
    cars_meta = read_header(CARS_FILE); cars_count = cars_meta.get('count', 0)
    cars = {}
    for i in range(cars_count):
        raw = read_record_at(CARS_FILE, i, CARS_RECORD_SIZE)
        if not raw: break
        c = unpack_car(raw); cars[c['car_id']] = c

    # load customers
    cust_meta = read_header(CUST_FILE); cust_count = cust_meta.get('count', 0)
    customers = {}
    for i in range(cust_count):
        raw = read_record_at(CUST_FILE, i, CUST_RECORD_SIZE)
        if not raw: break
        cu = unpack_customer(raw); customers[cu['cust_id']] = cu

    # load rentals
    rent_meta = read_header(RENT_FILE); rent_count = rent_meta.get('count', 0)
    rentals = []
    for i in range(rent_count):
        raw = read_record_at(RENT_FILE, i, RENT_RECORD_SIZE)
        if not raw: break
        r = unpack_rental(raw); rentals.append(r)

    # Section A: Customer-based report
    lines: List[str] = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.append('Car Rental Management System - Sample Reports')
    lines.append(f'Generated At: {now}')
    lines.append('')
    lines.append('=== Report A: Rentals by Customer (sample) ===')
    lines.append('+-------------+-------------------------+----------------+------------+------------+------+---------------+')
    lines.append('| Customer ID | Customer Name           | Car Rented     | Pick-up    | Return     | Days | Total Charge  |')
    lines.append('+-------------+-------------------------+----------------+------------+------------+------+---------------+')

    # pick up to 3 example rentals (if exist), else create mock examples from rentals list
    example_rows = []
    # prefer newest rentals to show variety
    rentals_sorted = sorted(rentals, key=lambda x: x['rent_id'])
    # take up to 3 real rentals
    for r in rentals_sorted[:3]:
        cust = customers.get(r['cust_id'], {'name':'Unknown'})
        car = cars.get(r['car_id'], {'brand':'Unknown','model':'Unknown'})
        pickup_dt = datetime.datetime.fromtimestamp(r['pickup_ts']).date()
        return_dt = pickup_dt + datetime.timedelta(days=r['days'])
        total = r['daily_rate'] * r['days']
        example_rows.append((
            f"C{r['cust_id']}",
            cust.get('name','Unknown'),
            f"{car.get('brand','')} {car.get('model','')}".strip(),
            pickup_dt.strftime('%Y-%m-%d'),
            return_dt.strftime('%Y-%m-%d'),
            str(r['days']),
            f"{total:.2f}"
        ))
    # if not enough rentals, fill with mock examples
    if len(example_rows) < 3:
        needed = 3 - len(example_rows)
        sample_customers = [
            ("C001","Mr. Somchai Jaidee"),
            ("C002","Ms. Kamoltip Nimnuan"),
            ("C003","Mr. Anan Srisuk"),
            ("C004","Ms. Lina Park")
        ]
        sample_cars = ["Toyota Vios","Honda Civic","Isuzu D-Max","Mazda 2"]
        base_date = datetime.date.today() - datetime.timedelta(days=9)
        for i in range(needed):
            cid, cname = sample_customers[i]
            car = sample_cars[i]
            pickup = base_date + datetime.timedelta(days=i*2)
            days = [3,2,6][i%3]
            rate = [900.0,1200.0,1500.0][i%3]
            total = rate*days
            example_rows.append((cid, cname, car, pickup.strftime('%Y-%m-%d'), (pickup + datetime.timedelta(days=days)).strftime('%Y-%m-%d'), str(days), f"{total:.2f}"))

    for er in example_rows:
        lines.append(f"| {er[0]:<11} | {er[1][:23]:<23} | {er[2][:14]:<14} | {er[3]:<10} | {er[4]:<10} | {er[5]:<4} | {er[6]:>13} |")
    lines.append('+-------------+-------------------------+----------------+------------+------------+------+---------------+')
    lines.append('')

    # Section B: Rental detail list (example)
    lines.append('=== Report B: Rental Details (sample) ===')
    lines.append('+--------+---------+-------------+------------+------------+------+----------+')
    lines.append('| RentID | Car ID  | Customer ID | Pick-up    | Return     | Days | Returned |')
    lines.append('+--------+---------+-------------+------------+------------+------+----------+')

    # show up to 6 rentals (real or mock)
    detail_rows = rentals_sorted[:6]
    # if none, create mock as above
    if not detail_rows:
        mock = [
            {'rent_id':1101,'car_id':1001,'cust_id':1001,'pickup_ts':int(time.mktime((datetime.date.today()-datetime.timedelta(days=7)).timetuple())),'daily_rate':900.0,'days':3,'is_returned':1},
            {'rent_id':1102,'car_id':1002,'cust_id':1002,'pickup_ts':int(time.mktime((datetime.date.today()-datetime.timedelta(days=5)).timetuple())),'daily_rate':1200.0,'days':2,'is_returned':1},
            {'rent_id':1103,'car_id':1003,'cust_id':1003,'pickup_ts':int(time.mktime((datetime.date.today()-datetime.timedelta(days=10)).timetuple())),'daily_rate':1500.0,'days':6,'is_returned':0}
        ]
        detail_rows = mock

    for r in detail_rows:
        pickup_dt = datetime.datetime.fromtimestamp(r['pickup_ts']).date()
        return_dt = pickup_dt + datetime.timedelta(days=r['days'])
        lines.append(f"| {r['rent_id']:<6} | {r['car_id']:<7} | C{r['cust_id']:<10} | {pickup_dt.strftime('%Y-%m-%d')} | {return_dt.strftime('%Y-%m-%d')} | {r['days']:<4} | {('Yes' if r['is_returned'] else 'No'):<8} |")
    lines.append('+--------+---------+-------------+------------+------------+------+----------+')
    lines.append('')

    # Section C: Car summary (reuse your existing summary logic)
    lines.append('=== Report C: Car Summary (Active only) ===')
    lines.append('+-------+------------+-----------+-----------+------+------------+---------+')
    lines.append('| CarID | Plate      | Brand     | Model     | Year | Rate (THB) | Status  |')
    lines.append('+-------+------------+-----------+-----------+------+------------+---------+')
    # active cars
    car_list = [v for v in cars.values() if v['status']==1]
    car_list = sorted(car_list, key=lambda x: x['car_id'])
    for c in car_list:
        st = 'Active' if c['status']==1 else 'Deleted'
        lines.append(f"| {c['car_id']:<5} | {c['license_plate'][:10]:<10} | {c['brand'][:9]:<9} | {c['model'][:9]:<9} | {c['year']:<4} | {c['daily_rate_thb']:<10.2f} | {st:<7} |")
    lines.append('+-------+------------+-----------+-----------+------+------------+---------+')
    lines.append('')
    total = len(car_list)
    rented = sum(1 for c in car_list if c['is_rented']==1)
    available = total - rented
    lines.append('Summary:')
    lines.append(f'- Active Cars     : {total}')
    lines.append(f'- Currently Rented: {rented}')
    lines.append(f'- Available Now   : {available}')
    if car_list:
        rates = [c['daily_rate_thb'] for c in car_list]
        lines.append(f'- Rate Min/Max/Avg: {min(rates):.2f} / {max(rates):.2f} / {sum(rates)/len(rates):.2f}')
    # Cars by brand
    brands = {}
    for c in car_list:
        b = c['brand'] or 'Unknown'
        brands[b] = brands.get(b, 0) + 1
    if brands:
        lines.append('')
        lines.append('Cars by Brand:')
        for k,v in sorted(brands.items(), key=lambda x: -x[1]):
            lines.append(f'- {k} : {v}')

    # write report to file
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Report written to {REPORT_FILE}. You can open this text file and hand it to your professor.")

# --- Sample data generators ---
BRANDS = ['Toyota','Honda','Nissan','Mazda','BMW','Mercedes','MG','Isuzu','Ford']
MODELS = ['Camry','Civic','Almera','2','Fortuner','530e','Yaris','Accord','C300','March']

def create_sample_cars(n: int = 50):
    ensure_file(CARS_FILE, CARS_RECORD_SIZE)
    meta = read_header(CARS_FILE)
    start_id = meta.get('next_id', 1001)
    for i in range(n):
        cid = start_id + i
        car = {
            'car_id': cid,
            'status': 1,
            'is_rented': 1 if random.random() < 0.3 else 0,
            'year': random.randint(2015, 2023),
            'daily_rate_thb': float(random.choice([800,900,1000,1200,1500,1800,2200,2500,3000])),
            'odometer_km': random.randint(5000,150000),
            'license_plate': ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=3)) + '-' + str(random.randint(1000,9999)),
            'brand': random.choice(BRANDS),
            'model': random.choice(MODELS),
            'created_at': int(time.time()),
            'updated_at': int(time.time())
        }
        append_record(CARS_FILE, pack_car(car), CARS_RECORD_SIZE)
    print(f'Created {n} sample car records (starting id {start_id})')

def create_sample_customers(n: int = 10):
    ensure_file(CUST_FILE, CUST_RECORD_SIZE)
    sample_names = [
        "Mr. Somchai Jaidee","Ms. Kamoltip Nimnuan","Mr. Anan Srisuk",
        "Ms. Lina Park","Mr. John Smith","Ms. Anna Lee","Mr. David Brown",
        "Ms. Sara Kim","Mr. Tom Jones","Ms. Maria Gomez"
    ]
    meta = read_header(CUST_FILE)
    start_id = meta.get('next_id', 1001)
    for i in range(n):
        cid = start_id + i
        name = sample_names[i % len(sample_names)]
        cust = {
            'cust_id': cid,
            'status': 1,
            'name': name,
            'phone': f'080-000-{1000 + i}',
            'email': f'user{cid}@example.com',
            'created_at': int(time.time()),
            'updated_at': int(time.time())
        }
        append_record(CUST_FILE, pack_customer(cust), CUST_RECORD_SIZE)
    print(f'Created {n} sample customers (starting id {start_id})')

def create_sample_rentals(n: int = 10):
    ensure_file(RENT_FILE, RENT_RECORD_SIZE)
    # we need cars and customers to exist
    ensure_file(CARS_FILE, CARS_RECORD_SIZE)
    ensure_file(CUST_FILE, CUST_RECORD_SIZE)
    cars_meta = read_header(CARS_FILE); cars_count = cars_meta.get('count', 0)
    cust_meta = read_header(CUST_FILE); cust_count = cust_meta.get('count', 0)
    if cars_count == 0 or cust_count == 0:
        print("Please create sample cars and customers first.")
        return
    car_ids = []
    for i in range(cars_count):
        raw = read_record_at(CARS_FILE, i, CARS_RECORD_SIZE)
        if not raw: break
        car_ids.append(unpack_car(raw)['car_id'])
    cust_ids = []
    for i in range(cust_count):
        raw = read_record_at(CUST_FILE, i, CUST_RECORD_SIZE)
        if not raw: break
        cust_ids.append(unpack_customer(raw)['cust_id'])

    meta = read_header(RENT_FILE)
    start_id = meta.get('next_id', 1001)
    base = datetime.date.today() - datetime.timedelta(days=30)
    for i in range(n):
        rid = start_id + i
        car_id = random.choice(car_ids)
        cust_id = random.choice(cust_ids)
        pickup = base + datetime.timedelta(days=random.randint(0, 25))
        days = random.choice([1,2,3,4,5,6,7])
        # read car daily rate if available
        idx = find_car_index_by_id(car_id)
        if idx is not None:
            car = unpack_car(read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE))
            rate = car['daily_rate_thb']
        else:
            rate = random.choice([900,1000,1200,1500])
        add_rental(car_id, cust_id, pickup, days, rate)
    print(f'Created {n} sample rentals (starting id {start_id})')

# --- Initialization and main menu ---
def initialize_all_files():
    ensure_file(CARS_FILE, CARS_RECORD_SIZE)
    ensure_file(CUST_FILE, CUST_RECORD_SIZE)
    ensure_file(RENT_FILE, RENT_RECORD_SIZE)
    print('Initialized files (if not present).')

MENU = '''
Main Menu:
1) Add Car
2) Update Car
3) Delete Car (logical)
4) View Cars
   a) View one
   b) View all
   c) View only Active
   d) View only Deleted
5) Generate Report (3 examples -> report.txt)
6) Create Sample Data
7) Customers (view/add)
8) Rentals (view/add)
0) Exit
Choose: '''

def sample_data_menu():
    print('Sample Data Menu:')
    print('1) Create 50 sample cars')
    print('2) Create 10 sample customers')
    print('3) Create 20 sample rentals (requires sample cars & customers)')
    print('0) Back')
    cmd = input('Choice: ').strip()
    if cmd == '1':
        create_sample_cars(50)
    elif cmd == '2':
        create_sample_customers(10)
    elif cmd == '3':
        create_sample_rentals(20)
    else:
        return

def customers_menu():
    print('Customers Menu:')
    print('1) View all customers')
    print('2) Add a customer (interactive)')
    print('0) Back')
    cmd = input('Choice: ').strip()
    if cmd == '1':
        view_all_customers()
    elif cmd == '2':
        name = input('Name: ').strip()
        phone = input('Phone: ').strip()
        email = input('Email: ').strip()
        cid = add_customer(name, phone, email)
        print(f'Added customer id {cid}')
    else:
        return

def rentals_menu():
    print('Rentals Menu:')
    print('1) View all rentals')
    print('2) Add a rental (interactive)')
    print('0) Back')
    cmd = input('Choice: ').strip()
    if cmd == '1':
        view_all_rentals()
    elif cmd == '2':
        try:
            car_id = int(input('Car ID: ').strip())
            cust_id = int(input('Customer ID: ').strip())
            pickup_str = input('Pick-up date (YYYY-MM-DD): ').strip()
            days = int(input('Days: ').strip())
            pickup_dt = datetime.datetime.strptime(pickup_str, '%Y-%m-%d').date()
            # get car rate if exists
            idx = find_car_index_by_id(car_id)
            rate = 1000.0
            if idx is not None:
                rate = unpack_car(read_record_at(CARS_FILE, idx, CARS_RECORD_SIZE))['daily_rate_thb']
            rid = add_rental(car_id, cust_id, pickup_dt, days, rate)
            print(f'Added rental id {rid}')
        except Exception as e:
            print('Invalid input or error:', e)
    else:
        return

def main_loop():
    initialize_all_files()
    while True:
        choice = input(MENU).strip()
        if choice == '1':
            add_car_interactive()
        elif choice == '2':
            update_car_interactive()
        elif choice == '3':
            delete_car_interactive()
        elif choice == '4':
            sub = input('a/b/c/d: ').strip().lower()
            if sub == 'a': view_one_car()
            elif sub == 'b': view_all_cars(None)
            elif sub == 'c': view_all_cars(True)
            elif sub == 'd': view_all_cars(False)
            else: print('Unknown')
        elif choice == '5':
            print('Generate Report:')
            print('a) Generate combined report (A,B,C) -> report.txt')
            print('b) Generate only Car Summary (old style)')
            c = input('Choice (a/b): ').strip().lower()
            if c == 'a':
                generate_report_all()
            else:
                generate_report_all()  # for simplicity we produce combined always
        elif choice == '6':
            sample_data_menu()
        elif choice == '7':
            customers_menu()
        elif choice == '8':
            rentals_menu()
        elif choice == '0':
            print('Exiting. Bye.')
            break
        else:
            print('Unknown choice')

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        print('\nInterrupted. Bye.')

import base64
import json

tokens = [
    "eyJhIjoiZjMyOWJkYWI0YmQ3NTI0NzJhY2JjYzVhMTMxMWJkMDciLCJ0IjoiZmM4NGE1NGMtMjdmZC00ZTg1LWJlYjctNGMxOTkzYWYyNGQ2IiwicyI6IlpqQmtOVEEwT1RVdE1UVTVOaTAwT0dRMUxXRTFNemN0TVRjek1qazNPV1kxTXpRMiJ9",
    "eyJhIjoiZjMyOWJkYWI0YmQ3NTI0NzJhY2JjYzVhMTMxMWJkMDciLCJ0IjoiZmIyY2Q3NGMtNTdjZi00ZmM5LTgxN2QtMWZlYWUzMWVmMzhmIiwicyI6Ik5ETmxNREJsTmpVdE1UZGpaQzAwWVdNMExXRXdOalV0TXpnd01qSmlOVFpsTm1GbSJ9",
]

for t in tokens:
    try:
        decoded = base64.b64decode(t).decode("utf-8")
        print(decoded)
    except Exception as e:
        print(e)

"""Critério único de qualidade meteorológica usado no portal e nas exportações.

Um registro está offline quando NÃO possui qualquer valor numérico de temperatura
E NÃO possui qualquer valor numérico de umidade. Zero, se medido, é informação.
"""
from math import isfinite

TEMPERATURE_FIELDS = ('temp_media_c', 'temp_min_c', 'temp_max_c')
HUMIDITY_FIELDS = ('umidade_media_pct', 'umidade_min_pct', 'umidade_max_pct')


def has_measurement(row, fields):
    for key in fields:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            if isfinite(float(value)):
                return True
        except (TypeError, ValueError, OverflowError):
            pass
    return False


def is_offline(row):
    return not has_measurement(row, TEMPERATURE_FIELDS) and not has_measurement(row, HUMIDITY_FIELDS)

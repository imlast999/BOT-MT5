"""
Parche para compatibilidad de audioop con Python 3.13
"""
import sys

# Instalar el parche para audioop
try:
    import audioop_lts as audioop
    sys.modules['audioop'] = audioop
except ImportError:
    pass
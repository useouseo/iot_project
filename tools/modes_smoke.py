"""Compatibility entry point for the multi-festival browser regression flow."""
import os
from unittest.mock import patch
from festivals_smoke import run
if __name__=='__main__':
    with patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test','RESTFLOW_TMAP_ROUTE_KEY':'test-route'}):run()

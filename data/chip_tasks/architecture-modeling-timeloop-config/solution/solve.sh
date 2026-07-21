#!/bin/sh
python3 - <<'PY'
from pathlib import Path

import yaml


path = Path("/workspace/arch.yaml")
payload = yaml.safe_load(path.read_text())
nodes = {node["name"]: node for node in payload["architecture"]["nodes"]}

nodes["DRAM"]["attributes"].update(width=64, datawidth=16)
nodes["shared_glb"]["attributes"].update(
    depth=16384,
    n_banks=32,
    read_bandwidth=16,
    write_bandwidth=16,
)
nodes["PE"]["spatial"].update(meshX=16, meshY=16)
nodes["pe_spad"]["attributes"]["depth"] = 192
nodes["pe_spad"]["constraints"]["dataspace"].update(
    keep=["Weights"],
    bypass=["Inputs", "Outputs"],
)
nodes["mac"]["attributes"].update(multiplier_width=8, adder_width=16)

path.write_text(yaml.safe_dump(payload, sort_keys=False))
PY

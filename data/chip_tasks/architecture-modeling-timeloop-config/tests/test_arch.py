from pathlib import Path

import yaml


payload = yaml.safe_load(Path("/workspace/arch.yaml").read_text())
assert payload["architecture"]["version"] == 0.4
nodes = {node["name"]: node for node in payload["architecture"]["nodes"]}
assert set(nodes) == {
    "system",
    "DRAM",
    "simple_ws",
    "shared_glb",
    "PE",
    "pe_spad",
    "mac",
}

dram = nodes["DRAM"]["attributes"]
assert dram["width"] == 64
assert dram["datawidth"] == 16

global_buffer = nodes["shared_glb"]["attributes"]
assert global_buffer["depth"] == 16384
assert global_buffer["n_banks"] == 32
assert global_buffer["read_bandwidth"] == 16
assert global_buffer["write_bandwidth"] == 16

mesh = nodes["PE"]["spatial"]
assert mesh == {"meshX": 16, "meshY": 16}
assert mesh["meshX"] * mesh["meshY"] == 256

scratchpad = nodes["pe_spad"]
assert scratchpad["attributes"]["depth"] == 192
dataspace = scratchpad["constraints"]["dataspace"]
assert set(dataspace["keep"]) == {"Weights"}
assert set(dataspace["bypass"]) == {"Inputs", "Outputs"}

mac = nodes["mac"]["attributes"]
assert mac == {"multiplier_width": 8, "adder_width": 16}

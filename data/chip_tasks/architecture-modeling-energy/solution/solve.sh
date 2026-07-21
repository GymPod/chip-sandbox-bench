#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def aggregate_energy(action_counts: dict, energy_per_action: dict) -> dict:
    components = {}
    for component, actions in action_counts.items():
        subtotal = 0.0
        for action, count in actions.items():
            energy = energy_per_action[component][action]
            if count < 0 or energy < 0:
                raise ValueError("negative energy input")
            subtotal += count * energy
        components[component] = subtotal
    return {"components": components, "total": sum(components.values())}
PY

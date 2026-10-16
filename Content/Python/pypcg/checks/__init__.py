"""V1 checks that need the editor's booleans or a recorded run: pypcg/checks/sNN.py defines
check(inputs, params, outputs, ops, official) -> [failure]. inputs is None when the run's inputs
cannot be recorded (a terrain surface); outputs are pypcg.geo values rebuilt from the run record;
official is {tag: [pypcg.geo values]} of the volume's current official output, or None."""

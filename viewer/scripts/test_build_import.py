import json
import tempfile
import unittest
from pathlib import Path

from build_import import build_import


class BuildImportTest(unittest.TestCase):
    def test_builds_task_and_file_documents(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            task = root / "sample"
            (task / "workspace").mkdir(parents=True)
            (task / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": "sample",
                        "discipline": "RTL Design",
                        "benchmark": "Sample",
                        "tools": ["iverilog"],
                        "source": {"repo": "sample", "commit": "abc", "paths": ["sample.sv"]},
                        "prompt": "Build it.",
                        "instruction": "Complete it.",
                    }
                ),
                encoding="utf-8",
            )
            (task / "workspace" / "sample.sv").write_text("module sample;\nendmodule\n", encoding="utf-8")

            tasks, files = build_import(root)

            self.assertEqual(tasks[0]["taskId"], "sample")
            self.assertNotIn("task_id", tasks[0])
            self.assertEqual(files[0]["path"], "workspace/sample.sv")
            self.assertEqual(files[0]["language"], "SystemVerilog")
            self.assertEqual(files[0]["content"], "module sample;\nendmodule\n")


if __name__ == "__main__":
    unittest.main()

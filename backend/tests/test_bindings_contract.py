"""Contract test: every delivered binding resolves against the delivered data model.

The backend does not resolve JSON-Pointer bindings (the frontend does), so this
walks the components it actually delivers and checks each `{"path": ...}` against
the data model it actually sends. It guards the flat-vs-`/finance` class of bug.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server

_MISSING = object()


def _resolve(path, model):
    node = model
    for part in path.split("/"):
        if part == "":
            continue
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        elif isinstance(node, dict):
            if part not in node:
                return _MISSING
            node = node[part]
        else:
            return _MISSING
    return node


def _collect_bindings(components):
    paths = []

    def visit(node):
        if isinstance(node, dict):
            if set(node.keys()) == {"path"} and isinstance(node["path"], str):
                paths.append(node["path"])
                return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for component in components:
        for key, value in component.items():
            if key in ("id", "component", "action"):
                continue
            visit(value)
    return paths


def _delivered(a2ui):
    components = next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]
    data_model = next(m for m in a2ui if "updateDataModel" in m)["updateDataModel"]["value"]
    return components, data_model


class BindingContractTest(unittest.TestCase):
    def test_debt_bindings_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "debt_bind.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"ui": build_ui_server(database)}) as toolbox:
                    persisted = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": "amitie.standard.v1",
                            "components": [
                                {"id": "root", "component": "Column", "children": ["debt"], "gap": 12},
                                {
                                    "id": "debt",
                                    "component": "DebtNode",
                                    "creditor": "BBVA",
                                    "balance": {"path": "/liabilities/0/balance"},
                                    "apr": {"path": "/liabilities/0/apr"},
                                    "minPayment": {"path": "/liabilities/0/minPayment"},
                                },
                            ],
                            "data_model": {},
                            "simulation": {"strategy": "avalanche"},
                        },
                    )
                    hydrated = await toolbox.call("hydrate_ui", {"surface_id": persisted["surface_id"]})
                components, data_model = _delivered(hydrated["a2ui"])
                bindings = _collect_bindings(components)
                self.assertTrue(bindings)
                for path in bindings:
                    self.assertIsNot(_resolve(path, data_model), _MISSING, f"unresolved binding {path}")
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

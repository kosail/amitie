import asyncio
import tempfile
import unittest
from pathlib import Path

from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from hydration.speech import speech_text
from mcp_servers.toolbox import InProcessToolbox
from mcp_servers.ui.server import build_ui_server
from ui_contract.catalog import STANDARD_CATALOG_ID, VOZ_COLOR_ID

COMPONENTS = [
    {"id": "root", "component": "Column", "children": ["h", "t"], "gap": 12},
    {"id": "h", "component": "Heading", "text": "Tu plan", "level": 1},
    {"id": "t", "component": "Text", "text": "Puedes ahorrar 3000 al mes"},
]


def _components(a2ui):
    return next(m for m in a2ui if "updateComponents" in m)["updateComponents"]["components"]


def _create_surface_id(a2ui):
    return next(m for m in a2ui if "createSurface" in m)["createSurface"]["catalogId"]


class SpeechTextTest(unittest.TestCase):
    def test_extracts_text(self) -> None:
        self.assertEqual(speech_text(COMPONENTS), "Tu plan. Puedes ahorrar 3000 al mes")

    def test_handles_options(self) -> None:
        components = [
            {
                "id": "c",
                "component": "ChoiceGroup",
                "options": [{"value": "a", "label": "Mochilero"}, {"value": "b", "label": "Confort"}],
            }
        ]
        self.assertEqual(speech_text(components), "Mochilero. Confort")


class AccessibilityPinningTest(unittest.TestCase):
    def test_ana_stays_standard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "a11y.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"ui": build_ui_server(database)}) as toolbox:
                    result = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_ana",
                            "domain": "loans_credits",
                            "catalog_id": STANDARD_CATALOG_ID,
                            "components": COMPONENTS,
                            "data_model": {},
                        },
                    )
                    self.assertEqual(result["status"], "ok", result)
                    self.assertFalse(result["accessible"])
                    self.assertEqual(result["catalog_id"], STANDARD_CATALOG_ID)
                    self.assertEqual(_create_surface_id(result["a2ui"]), STANDARD_CATALOG_ID)
                await database.close()

            asyncio.run(run())

    def test_don_is_pinned_to_voz_color_with_speech(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = LocalSQLiteDatabase(Path(tmp) / "a11y.sqlite3")

            async def run() -> None:
                await apply_schema(database)
                await seed(database)
                async with InProcessToolbox({"ui": build_ui_server(database)}) as toolbox:
                    result = await toolbox.call(
                        "persist_ui",
                        {
                            "user_id": "u_don",
                            "domain": "loans_credits",
                            "catalog_id": STANDARD_CATALOG_ID,
                            "components": COMPONENTS,
                            "data_model": {},
                        },
                    )
                    self.assertEqual(result["status"], "ok", result)
                    self.assertTrue(result["accessible"])
                    self.assertEqual(result["catalog_id"], VOZ_COLOR_ID)
                    self.assertEqual(_create_surface_id(result["a2ui"]), VOZ_COLOR_ID)
                    self.assertEqual(result["speech"], "Tu plan. Puedes ahorrar 3000 al mes")

                    hydrated = await toolbox.call(
                        "hydrate_ui", {"surface_id": result["surface_id"]}
                    )
                    data_model = next(
                        m for m in hydrated["a2ui"] if "updateDataModel" in m
                    )["updateDataModel"]["value"]
                    self.assertEqual(data_model["speech"]["text"], result["speech"])
                    self.assertNotIn("audioRef", data_model["speech"])
                await database.close()

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

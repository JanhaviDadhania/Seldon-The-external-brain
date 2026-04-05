from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.edge_creation_ops import InternalTags, _extract_internal_tags, _extract_internal_tags_batch
from app.main import create_app
from app.telegram_ingest import classify_telegram_text


class AppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        settings = Settings(
            app_name="twitter-poster-backend-test",
            environment="test",
            database_url=f"sqlite:///{db_path}",
            use_ollama_for_internal_tags=False,
            preload_embedding_model_on_startup=False,
            telegram_bot_token=None,
        )
        self.client = TestClient(create_app(settings))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_setup_status_is_ready_when_preload_disabled(self) -> None:
        response = self.client.get("/setup-status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_frontend_index_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Poll Telegram", response.text)
        self.assertIn("Automatically Generate Edges", response.text)
        self.assertIn("Zoom In", response.text)
        self.assertIn("Zoom Out", response.text)
        self.assertIn("Reset Zoom", response.text)
        self.assertIn("Generate Narrative Off", response.text)
        self.assertIn("Path Tracing Off", response.text)
        self.assertIn("Create Edge", response.text)
        self.assertIn("Cancel Selection", response.text)
        self.assertIn("Review Proposed Links", response.text)
        self.assertIn("Developer Mode Off", response.text)
        self.assertIn("graph-svg", response.text)
        self.assertIn("Add Node", response.text)

    def test_advanced_page_is_served(self) -> None:
        response = self.client.get("/advanced")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Traversal", response.text)
        self.assertIn("Edge Creation", response.text)
        self.assertIn("Node Neighborhood", response.text)
        self.assertIn("Outline Planning", response.text)
        self.assertIn("Tag Matcher", response.text)

    def test_embed_page_is_served(self) -> None:
        response = self.client.get("/embed")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Workspace Embed", response.text)

    def test_ontology_endpoint(self) -> None:
        response = self.client.get("/ontology")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("idea", payload["node_types"])
        self.assertIn("supports", payload["edge_types"])

    def test_telegram_config_endpoint_defaults_to_unconfigured(self) -> None:
        response = self.client.get("/telegram/config")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["configured"])
        self.assertIsNone(response.json()["stored_offset"])
        self.assertEqual(response.json()["current_workspace_name"], "maker graph")

    def test_default_workspace_is_bootstrapped(self) -> None:
        response = self.client.get("/workspaces/current")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "maker graph")
        self.assertEqual(payload["type"], "general")
        self.assertTrue(payload["embed_token"])

        all_workspaces = self.client.get("/workspaces")
        self.assertEqual(all_workspaces.status_code, 200)
        self.assertEqual(len(all_workspaces.json()), 1)

    def test_workspace_switch_isolates_graph_data(self) -> None:
        maker = self.client.get("/workspaces/current").json()
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "maker workspace note", "source": "manual"},
        ).json()

        switched = self.client.post("/workspaces/switch", json={"workspace_name": "mars graph"})
        self.assertEqual(switched.status_code, 200)
        mars = switched.json()
        self.assertEqual(mars["name"], "mars graph")

        node_b = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "mars workspace note", "source": "manual"},
        ).json()
        self.assertEqual(node_b["workspace_id"], mars["id"])

        maker_graph = self.client.get(f"/graph-data?workspace_id={maker['id']}")
        self.assertEqual(maker_graph.status_code, 200)
        self.assertEqual([node["id"] for node in maker_graph.json()["nodes"]], [node_a["id"]])

        mars_graph = self.client.get(f"/graph-data?workspace_id={mars['id']}")
        self.assertEqual(mars_graph.status_code, 200)
        self.assertEqual([node["id"] for node in mars_graph.json()["nodes"]], [node_b["id"]])

    def test_timeaware_workspace_allows_timed_nodes(self) -> None:
        workspace = self.client.post(
            "/workspaces/switch",
            json={"workspace_name": "ai timeline", "workspace_type": "time_aware"},
        ).json()
        response = self.client.post(
            "/nodes",
            json={
                "workspace_id": workspace["id"],
                "type": "idea",
                "raw_text": "Attention Is All You Need #transformers #nlp",
                "time_label": "2017",
                "tags": ["transformers", "nlp"],
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["workspace_id"], workspace["id"])
        self.assertEqual(payload["metadata_json"]["time"]["label"], "2017")
        self.assertEqual(payload["metadata_json"]["time"]["year"], 2017)

    def test_general_workspace_rejects_time_label(self) -> None:
        workspace = self.client.get("/workspaces/current").json()
        response = self.client.post(
            "/nodes",
            json={
                "workspace_id": workspace["id"],
                "type": "idea",
                "raw_text": "A normal maker note",
                "time_label": "2017",
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_embed_graph_data_requires_valid_token(self) -> None:
        workspace = self.client.get("/workspaces/current").json()
        node = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "embed me", "source": "manual"},
        ).json()

        forbidden = self.client.get(f"/embed/graph-data?workspace_id={workspace['id']}&token=wrong")
        self.assertEqual(forbidden.status_code, 403)

        allowed = self.client.get(
            f"/embed/graph-data?workspace_id={workspace['id']}&token={workspace['embed_token']}"
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual([item["id"] for item in allowed.json()["nodes"]], [node["id"]])

    def test_telegram_command_switches_active_workspace(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 106,
                    "message": {
                        "message_id": 82,
                        "date": 1710000005,
                        "text": "switch workspace to mars field notes",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "switched_workspace")

        current = self.client.get("/workspaces/current")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["name"], "mars field notes")

        node_response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 107,
                    "message": {
                        "message_id": 83,
                        "date": 1710000006,
                        "text": "mars soil samples are behaving strangely",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(node_response.status_code, 201)
        self.assertEqual(node_response.json()["node"]["workspace_id"], current.json()["id"])

    def test_telegram_command_creates_timeaware_workspace(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 108,
                    "message": {
                        "message_id": 84,
                        "date": 1710000007,
                        "text": "switch workspace to timeaware ai progress timeline",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "switched_workspace")

        current = self.client.get("/workspaces/current")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["name"], "ai progress timeline")
        self.assertEqual(current.json()["type"], "time_aware")

    def test_telegram_switch_to_existing_workspace_name(self) -> None:
        created = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 109,
                    "message": {
                        "message_id": 85,
                        "date": 1710000008,
                        "text": "switch workspace to timeaware mars chronology",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(created.status_code, 200)

        switched_back = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 110,
                    "message": {
                        "message_id": 86,
                        "date": 1710000009,
                        "text": "switch to mars chronology",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(switched_back.status_code, 200)
        self.assertEqual(switched_back.json()["outcome"], "switched_workspace")

        current = self.client.get("/workspaces/current")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["name"], "mars chronology")
        self.assertEqual(current.json()["type"], "time_aware")

    def test_embeddings_config_endpoint_defaults(self) -> None:
        response = self.client.get("/embeddings/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["model_name"], "sentence-transformers/all-mpnet-base-v2")

    def test_classify_telegram_text_by_length(self) -> None:
        self.assertEqual(classify_telegram_text("short thought"), "line")
        self.assertEqual(classify_telegram_text("x" * 180), "idea")
        self.assertEqual(classify_telegram_text("x" * 800), "thought_piece")
        self.assertEqual(classify_telegram_text("x" * 1800), "document")

    def test_telegram_ingest_creates_node_with_heuristic_type(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 101,
                    "message": {
                        "message_id": 77,
                        "date": 1710000000,
                        "text": "x" * 180,
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["outcome"], "created")
        self.assertEqual(payload["node"]["type"], "idea")
        self.assertEqual(payload["node"]["telegram_message_id"], "12345:77")
        self.assertEqual(payload["node"]["tags"], [])

    def test_telegram_ingest_extracts_optional_hashtag_tags(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 104,
                    "message": {
                        "message_id": 80,
                        "date": 1710000003,
                        "text": "Software should adapt like organisms. #biology #software #agency",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["node"]["tags"], ["biology", "software", "agency"])
        self.assertEqual(
            payload["node"]["raw_text"],
            "Software should adapt like organisms.",
        )

    def test_telegram_ingest_supports_explicit_topic_prefix(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 105,
                    "message": {
                        "message_id": 81,
                        "date": 1710000004,
                        "text": "topic: biological software organs #biology #modularity",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["node"]["type"], "topic")
        self.assertEqual(payload["node"]["raw_text"], "biological software organs")
        self.assertEqual(payload["node"]["tags"], ["biology", "modularity"])

    def test_telegram_ingest_ignores_empty_text(self) -> None:
        response = self.client.post(
            "/telegram/ingest",
            json={
                "update": {
                    "update_id": 102,
                    "message": {
                        "message_id": 78,
                        "date": 1710000001,
                        "text": "   ",
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 900, "username": "janhavi"},
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["outcome"], "ignored")
        self.assertIsNone(payload["node"])

        nodes = self.client.get("/nodes").json()
        self.assertEqual(nodes, [])

    def test_telegram_ingest_is_idempotent_for_duplicate_update_id(self) -> None:
        update = {
            "update": {
                "update_id": 103,
                "message": {
                    "message_id": 79,
                    "date": 1710000002,
                    "text": "Adaptive systems should be editable but stable.",
                    "chat": {"id": 12345, "type": "private"},
                    "from": {"id": 900, "username": "janhavi"},
                },
            }
        }

        first = self.client.post("/telegram/ingest", json=update)
        second = self.client.post("/telegram/ingest", json=update)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["outcome"], "duplicate")

        nodes = self.client.get("/nodes").json()
        self.assertEqual(len(nodes), 1)

    def test_telegram_poll_persists_and_reuses_offset(self) -> None:
        calls: list[int | None] = []

        async def fake_poll(settings, offset=None):
            calls.append(offset)
            if len(calls) == 1:
                return [
                    {
                        "update_id": 200,
                        "message": {
                            "message_id": 1,
                            "date": 1710000100,
                            "text": "first telegram note",
                            "chat": {"id": 12345, "type": "private"},
                            "from": {"id": 900, "username": "janhavi"},
                        },
                    }
                ]
            return []

        with patch("app.main.poll_telegram_updates", new=fake_poll):
            first = self.client.post("/telegram/poll")
            second = self.client.post("/telegram/poll")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(calls, [None, 201])
        self.assertEqual(first.json()["used_offset"], None)
        self.assertEqual(first.json()["next_offset"], 201)
        self.assertEqual(second.json()["used_offset"], 201)

        config = self.client.get("/telegram/config")
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json()["stored_offset"], 201)

    def test_internal_tag_extraction_uses_ollama_when_enabled(self) -> None:
        settings = Settings(
            app_name="twitter-poster-ollama-test",
            environment="test",
            database_url="sqlite:///unused.db",
            use_ollama_for_internal_tags=True,
            preload_embedding_model_on_startup=False,
            telegram_bot_token=None,
        )

        with patch(
            "app.edge_creation_ops._request_ollama_tags_batch",
            return_value=[
                InternalTags(
                    keywords=["softwaresystems", "biologicalsystems"],
                    concepts=["cybernetics", "systemdesign"],
                )
            ],
        ) as mocked:
            tags = _extract_internal_tags("software systems should be designed like biological systems", settings=settings)

        mocked.assert_called_once()
        self.assertEqual(tags.keywords, ["softwaresystems", "biologicalsystems"])
        self.assertEqual(tags.concepts, ["cybernetics", "systemdesign"])

    def test_internal_tag_batch_extraction_uses_single_ollama_batch_call(self) -> None:
        settings = Settings(
            app_name="twitter-poster-ollama-batch-test",
            environment="test",
            database_url="sqlite:///unused.db",
            use_ollama_for_internal_tags=True,
            preload_embedding_model_on_startup=False,
            telegram_bot_token=None,
        )

        with patch(
            "app.edge_creation_ops._request_ollama_tags_batch",
            return_value=[
                InternalTags(keywords=["software"], concepts=["biology"]),
                InternalTags(keywords=["organ"], concepts=["cybernetics"]),
            ],
        ) as mocked:
            tags = _extract_internal_tags_batch(
                [
                    "software systems should be designed like biological systems",
                    "software organisms may share organs",
                ],
                settings=settings,
            )

        mocked.assert_called_once()
        self.assertEqual(len(tags), 2)
        self.assertEqual(tags[0].concepts, ["biology"])
        self.assertEqual(tags[1].concepts, ["cybernetics"])

    def test_create_node_and_roundtrip_metadata(self) -> None:
        response = self.client.post(
            "/nodes",
            json={
                "type": "idea",
                "raw_text": "Adaptive software should learn from context.",
                "source": "telegram",
                "metadata_json": {"origin": "test"},
                "tags": ["adaptive", "software"],
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["type"], "idea")
        self.assertEqual(payload["metadata_json"]["origin"], "test")
        self.assertEqual(payload["tags"], ["adaptive", "software"])
        self.assertIn("normalization", payload["metadata_json"])
        self.assertEqual(payload["normalized_text"], "Adaptive software should learn from context.")

    def test_graph_data_returns_nodes_and_edges(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Adaptive software", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "Biological systems", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={
                "from_node_id": node_a["id"],
                "to_node_id": node_b["id"],
                "type": "belongs_to_topic",
                "weight": 0.8,
            },
        )

        response = self.client.get("/graph-data")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["edges"]), 1)
        self.assertEqual(payload["nodes"][0]["id"], node_a["id"])
        self.assertIn("linker_tags", payload["nodes"][0])
        self.assertIn("keywords", payload["nodes"][0]["linker_tags"])
        self.assertIn("concepts", payload["nodes"][0]["linker_tags"])
        self.assertEqual(payload["edges"][0]["type"], "belongs_to_topic")

    def test_generate_narrative_uses_subgraph_and_returns_text(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Software should evolve like organisms.", "source": "manual"},
        ).json()
        child = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Modular organs could be reused across systems.", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={
                "from_node_id": root["id"],
                "to_node_id": child["id"],
                "type": "led_to",
                "weight": 0.9,
            },
        )

        with patch("app.narrative_ops.httpx.post") as mocked_post:
            mocked_post.return_value.json.return_value = {
                "response": '{"narrative":"This idea begins with software behaving more like living systems. It then moves toward reusable organs and modular growth.\\n\\nThe resulting direction is a more biological view of software architecture, where parts can evolve and recombine over time."}'
            }
            mocked_post.return_value.raise_for_status.return_value = None

            response = self.client.post(
                "/narratives/generate",
                json={"root_node_id": root["id"], "depth": 2, "max_nodes": 9, "paragraphs": 2},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["root_node"]["id"], root["id"])
        self.assertIn("software behaving more like living systems", payload["narrative"].lower())
        self.assertGreaterEqual(len(payload["nodes"]), 2)

    def test_tag_matcher_endpoint_returns_isolated_edge_proposals(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software grows through organs.", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Software organs should grow like biology.", "source": "manual"},
        ).json()

        response = self.client.post(
            "/edge-creation/tag_matcher",
            json={
                "function_name": "tag_matcher",
                "node_ids": [node_a["id"], node_b["id"]],
                "config": {"edge_types_allowed": ["similar_to", "belongs_to_topic"]},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["function_name"], "tag_matcher")
        self.assertGreaterEqual(payload["summary"]["edges_proposed"], 1)
        self.assertEqual(payload["edges"][0]["metadata"]["function_name"], "tag_matcher")

    def test_tag_matcher_reuses_stored_linker_tags_without_regeneration(self) -> None:
        with patch("app.edge_creation_ops._extract_internal_tags_batch") as mocked_batch:
            response = self.client.post(
                "/edge-creation/tag_matcher",
                json={
                    "function_name": "tag_matcher",
                    "nodes": [
                        {
                            "id": 6,
                            "type": "idea",
                            "raw_text": "software should evolve like biological organisms",
                            "normalized_text": "software should evolve like biological organisms",
                            "user_tags": [],
                            "metadata": {
                                "linker_tags": {
                                    "keywords": ["software", "organism"],
                                    "concepts": ["biology", "complex_systems"],
                                }
                            },
                        },
                        {
                            "id": 12,
                            "type": "idea",
                            "raw_text": "software organisms should adapt biologically",
                            "normalized_text": "software organisms should adapt biologically",
                            "user_tags": [],
                            "metadata": {
                                "linker_tags": {
                                    "keywords": ["software", "organism"],
                                    "concepts": ["biology", "adaptive_systems"],
                                }
                            },
                        },
                    ],
                    "pairs": [{"source_node_id": 6, "target_node_id": 12}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["summary"]["edges_proposed"], 1)
        mocked_batch.assert_not_called()

    def test_hub_matcher_endpoint_returns_and_persists_hubs(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software uses reusable organs.", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Reusable organs can compose larger software organisms.", "source": "manual"},
        ).json()

        response = self.client.post(
            "/edge-creation/hub_matcher",
            json={
                "function_name": "hub_matcher",
                "node_ids": [node_a["id"], node_b["id"]],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["function_name"], "hub_matcher")
        self.assertGreaterEqual(payload["summary"]["hubs_proposed"], 1)
        self.assertGreaterEqual(len(payload["hubs"]), 1)

    def test_generate_edges_action_creates_edges(self) -> None:
        self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly.", "source": "manual"},
        )
        self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly in context.", "source": "manual"},
        )
        response = self.client.post("/graph/actions/generate-edges")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["queued_embeddings"], 0)
        self.assertGreaterEqual(payload["queued_links"], 2)
        self.assertGreaterEqual(payload["link_processing"]["edges_created"], 1)

    def test_generate_edges_backfills_legacy_nodes_missing_linker_tags(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly.", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly in context.", "source": "manual"},
        ).json()

        self.client.patch(
            f"/nodes/{node_a['id']}",
            json={"metadata_json": {"normalization": node_a["metadata_json"]["normalization"]}, "reason": "legacy_reset"},
        )
        self.client.patch(
            f"/nodes/{node_b['id']}",
            json={"metadata_json": {"normalization": node_b["metadata_json"]["normalization"]}, "reason": "legacy_reset"},
        )

        response = self.client.post("/graph/actions/generate-edges")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["link_processing"]["edges_created"], 1)

    def test_node_update_creates_version_and_persists_manual_type_correction(self) -> None:
        node = self.client.post(
            "/nodes",
            json={
                "type": "line",
                "raw_text": "  This   should\nstay raw but normalize cleanly.  ",
                "source": "manual",
            },
        ).json()

        update = self.client.patch(
            f"/nodes/{node['id']}",
            json={
                "type": "quote",
                "tags": ["edited", "manual"],
                "reason": "manual_type_correction",
            },
        )
        self.assertEqual(update.status_code, 200)
        payload = update.json()
        self.assertEqual(payload["type"], "quote")
        self.assertEqual(payload["tags"], ["edited", "manual"])
        self.assertEqual(
            payload["normalized_text"],
            "This should stay raw but normalize cleanly.",
        )
        self.assertEqual(
            payload["raw_text"],
            "This   should\nstay raw but normalize cleanly.",
        )

        versions = self.client.get(f"/nodes/{node['id']}/versions")
        self.assertEqual(versions.status_code, 200)
        version_payload = versions.json()
        self.assertEqual(len(version_payload), 1)
        self.assertEqual(version_payload[0]["reason"], "manual_type_correction")
        self.assertEqual(version_payload[0]["snapshot_json"]["type"], "line")

    def test_soft_deleted_nodes_are_hidden_by_default(self) -> None:
        node = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Delete me later", "source": "manual"},
        ).json()

        delete_response = self.client.delete(f"/nodes/{node['id']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")

        nodes = self.client.get("/nodes")
        self.assertEqual(nodes.status_code, 200)
        self.assertEqual(nodes.json(), [])

        deleted_nodes = self.client.get("/nodes?include_deleted=true")
        self.assertEqual(deleted_nodes.status_code, 200)
        self.assertEqual(len(deleted_nodes.json()), 1)

    def test_node_update_recomputes_normalization_without_overwriting_raw_text(self) -> None:
        node = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Alpha", "source": "manual"},
        ).json()

        update = self.client.patch(
            f"/nodes/{node['id']}",
            json={
                "raw_text": "  Alpha\n\nBeta   Gamma  ",
                "reason": "content_edit",
            },
        )
        self.assertEqual(update.status_code, 200)
        payload = update.json()
        self.assertEqual(payload["raw_text"], "Alpha\n\nBeta   Gamma")
        self.assertEqual(payload["normalized_text"], "Alpha Beta Gamma")
        self.assertEqual(
            payload["metadata_json"]["normalization"]["summary"],
            "Alpha Beta Gamma",
        )
        self.assertIn("linker_tags", payload["metadata_json"])
        self.assertTrue(payload["metadata_json"]["linker_tags"]["keywords"])

    def test_embedding_jobs_process_and_retrieve_candidates(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={
                "type": "idea",
                "raw_text": "Biological software adapts like living organisms.",
                "source": "manual",
            },
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={
                "type": "idea",
                "raw_text": "Adaptive software should evolve like organisms.",
                "source": "manual",
            },
        ).json()
        self.client.post(
            "/nodes",
            json={
                "type": "idea",
                "raw_text": "A recipe for baking bread with olive oil.",
                "source": "manual",
            },
        )

        def fake_embed(settings, model_name, text):
            lowered = text.lower()
            if "organism" in lowered or "biological" in lowered or "adaptive" in lowered:
                return [1.0, 0.0]
            return [0.0, 1.0]

        with patch("app.embedding_ops._embed_text", new=fake_embed):
            process = self.client.post("/embeddings/jobs/process")
            self.assertEqual(process.status_code, 200)
            self.assertEqual(process.json()["processed"], 3)

        embeddings_a = self.client.get(f"/nodes/{node_a['id']}/embeddings")
        self.assertEqual(embeddings_a.status_code, 200)
        self.assertEqual(len(embeddings_a.json()), 1)

        candidates = self.client.get(f"/nodes/{node_a['id']}/candidates")
        self.assertEqual(candidates.status_code, 200)
        payload = candidates.json()
        self.assertGreaterEqual(len(payload), 2)
        self.assertEqual(payload[0]["node"]["id"], node_b["id"])
        self.assertGreater(payload[0]["combined_score"], payload[1]["combined_score"])

    def test_node_update_queues_reembedding_for_new_content(self) -> None:
        node = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Original note", "source": "manual"},
        ).json()

        def fake_embed(settings, model_name, text):
            return [float(len(text)), 1.0]

        with patch("app.embedding_ops._embed_text", new=fake_embed):
            first_process = self.client.post("/embeddings/jobs/process")
            self.assertEqual(first_process.status_code, 200)
            self.assertEqual(first_process.json()["processed"], 1)

            update = self.client.patch(
                f"/nodes/{node['id']}",
                json={"raw_text": "Original note with more content", "reason": "expand"},
            )
            self.assertEqual(update.status_code, 200)

            second_process = self.client.post("/embeddings/jobs/process")
            self.assertEqual(second_process.status_code, 200)
            self.assertEqual(second_process.json()["processed"], 1)

        embeddings = self.client.get(f"/nodes/{node['id']}/embeddings")
        self.assertEqual(embeddings.status_code, 200)
        self.assertEqual(len(embeddings.json()), 2)

    def test_link_jobs_create_edges_for_confident_matches(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Adaptive software behaves like organisms.", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Adaptive software behaves like living organisms.", "source": "manual"},
        ).json()

        process_links = self.client.post("/link-jobs/process")
        self.assertEqual(process_links.status_code, 200)
        self.assertGreaterEqual(process_links.json()["edges_created"], 1)

        edges = self.client.get("/edges").json()
        self.assertTrue(
            any(
                edge["from_node_id"] == node_a["id"]
                and edge["to_node_id"] == node_b["id"]
                for edge in edges
            )
        )

    def test_link_jobs_connect_idea_to_topic_via_shared_tags(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Reusable organs can compose software organisms.", "source": "manual"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "software organs", "source": "manual"},
        ).json()

        process_links = self.client.post("/link-jobs/process")
        self.assertEqual(process_links.status_code, 200)
        edges = self.client.get("/edges").json()
        self.assertTrue(
            any(
                edge["from_node_id"] == node_a["id"]
                and edge["to_node_id"] == node_b["id"]
                and edge["type"] == "belongs_to_topic"
                for edge in edges
            )
        )

    def test_duplicate_link_processing_does_not_duplicate_edges(self) -> None:
        self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly.", "source": "manual"},
        )
        self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Biological software adapts quickly in context.", "source": "manual"},
        )

        first = self.client.post("/link-jobs/process")
        second = self.client.post("/link-jobs/process")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        edges = self.client.get("/edges").json()
        self.assertEqual(len(edges), 1)

    def test_neighbors_can_be_filtered_by_edge_type(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root idea", "source": "manual"},
        ).json()
        support = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Support idea", "source": "manual"},
        ).json()
        topic = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "Biological software", "source": "manual"},
        ).json()

        self.client.post(
            "/edges",
            json={
                "from_node_id": root["id"],
                "to_node_id": support["id"],
                "type": "supports",
                "weight": 0.9,
            },
        )
        self.client.post(
            "/edges",
            json={
                "from_node_id": root["id"],
                "to_node_id": topic["id"],
                "type": "belongs_to_topic",
                "weight": 0.8,
            },
        )

        response = self.client.get(f"/nodes/{root['id']}/neighbors?edge_type=supports")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["edge"]["type"], "supports")
        self.assertEqual(payload[0]["node"]["id"], support["id"])

    def test_subgraph_traversal_prefers_stronger_edges(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root idea", "source": "manual"},
        ).json()
        strong = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Strong path", "source": "manual"},
        ).json()
        weak = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Weak path", "source": "manual"},
        ).json()

        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": weak["id"], "type": "supports", "weight": 0.2},
        )
        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": strong["id"], "type": "supports", "weight": 0.9},
        )

        response = self.client.get(f"/nodes/{root['id']}/subgraph?depth=1&limit=3")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        self.assertEqual(nodes[1]["node"]["id"], strong["id"])
        self.assertGreater(nodes[1]["path_score"], nodes[2]["path_score"])

    def test_subgraph_excludes_deleted_nodes(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root idea", "source": "manual"},
        ).json()
        deleted = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Deleted node", "source": "manual"},
        ).json()

        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": deleted["id"], "type": "supports", "weight": 0.9},
        )
        self.client.delete(f"/nodes/{deleted['id']}")

        response = self.client.get(f"/nodes/{root['id']}/subgraph")
        self.assertEqual(response.status_code, 200)
        node_ids = [item["node"]["id"] for item in response.json()["nodes"]]
        self.assertNotIn(deleted["id"], node_ids)

    def test_topic_centered_subgraph_loads(self) -> None:
        topic = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "Biological software", "source": "manual"},
        ).json()
        note = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Software can adapt like organisms.", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={
                "from_node_id": note["id"],
                "to_node_id": topic["id"],
                "type": "belongs_to_topic",
                "weight": 0.85,
            },
        )

        response = self.client.get(f"/nodes/{topic['id']}/subgraph?depth=1&limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["root_node"]["id"], topic["id"])
        self.assertTrue(any(item["node"]["id"] == note["id"] for item in payload["nodes"]))

    def test_outline_planner_produces_stable_ordering(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root idea", "source": "manual"},
        ).json()
        support = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Support path", "source": "manual"},
        ).json()
        contradiction = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "But maybe not", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": support["id"], "type": "supports", "weight": 0.9},
        )
        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": contradiction["id"], "type": "contradicts", "weight": 0.4},
        )

        first = self.client.post("/outlines/plan", json={"root_node_id": root["id"], "depth": 1, "max_nodes": 6})
        second = self.client.post("/outlines/plan", json={"root_node_id": root["id"], "depth": 1, "max_nodes": 6})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["sections"], second.json()["sections"])

    def test_article_draft_generation_keeps_provenance(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Software should adapt to context.", "source": "manual"},
        ).json()
        support = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Adaptive systems learn from feedback loops.", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": support["id"], "type": "supports", "weight": 0.8},
        )

        response = self.client.post("/article-drafts", json={"root_node_id": root["id"], "depth": 1})
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIn("#", payload["content_markdown"])
        self.assertTrue(payload["provenance_json"])
        self.assertIn(root["id"], payload["provenance_json"][0]["node_ids"])

    def test_article_draft_edit_creates_version(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root article idea", "source": "manual"},
        ).json()
        draft = self.client.post("/article-drafts", json={"root_node_id": root["id"]}).json()

        update = self.client.patch(
            f"/article-drafts/{draft['id']}",
            json={"title": "Edited Title", "reason": "manual_revision"},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["title"], "Edited Title")

        versions = self.client.get(f"/article-drafts/{draft['id']}/versions")
        self.assertEqual(versions.status_code, 200)
        payload = versions.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["reason"], "manual_revision")

    def test_article_export_returns_markdown(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Exportable thought", "source": "manual"},
        ).json()
        draft = self.client.post("/article-drafts", json={"root_node_id": root["id"]}).json()

        response = self.client.get(f"/article-drafts/{draft['id']}/export")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("markdown", payload)
        self.assertTrue(payload["markdown"].startswith("# "))

    def test_deleted_source_nodes_are_not_used_in_new_drafts(self) -> None:
        root = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Root article idea", "source": "manual"},
        ).json()
        deleted = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Discarded thought", "source": "manual"},
        ).json()
        self.client.post(
            "/edges",
            json={"from_node_id": root["id"], "to_node_id": deleted["id"], "type": "supports", "weight": 0.9},
        )
        self.client.delete(f"/nodes/{deleted['id']}")

        draft = self.client.post("/article-drafts", json={"root_node_id": root["id"], "depth": 1})
        self.assertEqual(draft.status_code, 201)
        payload = draft.json()
        self.assertNotIn("Discarded thought", payload["content_markdown"])

    def test_invalid_node_type_is_rejected(self) -> None:
        response = self.client.post(
            "/nodes",
            json={"type": "nonsense", "raw_text": "bad"},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_edge_requires_existing_nodes(self) -> None:
        response = self.client.post(
            "/edges",
            json={
                "from_node_id": 1,
                "to_node_id": 2,
                "type": "supports",
                "weight": 0.8,
                "confidence": 0.9,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_create_edge_between_existing_nodes(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "A", "source": "test"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "B", "source": "test"},
        ).json()

        response = self.client.post(
            "/edges",
            json={
                "from_node_id": node_a["id"],
                "to_node_id": node_b["id"],
                "type": "belongs_to_topic",
                "weight": 0.75,
                "confidence": 0.66,
                "created_by": "test",
                "metadata_json": {"reason": "manual test"},
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["type"], "belongs_to_topic")
        self.assertEqual(payload["metadata_json"]["reason"], "manual test")

    def test_delete_edge_removes_it_from_list(self) -> None:
        node_a = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "A", "source": "test"},
        ).json()
        node_b = self.client.post(
            "/nodes",
            json={"type": "topic", "raw_text": "B", "source": "test"},
        ).json()

        edge = self.client.post(
            "/edges",
            json={
                "from_node_id": node_a["id"],
                "to_node_id": node_b["id"],
                "type": "belongs_to_topic",
            },
        ).json()

        get_response = self.client.get(f"/edges/{edge['id']}")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["id"], edge["id"])

        delete_response = self.client.delete(f"/edges/{edge['id']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["id"], edge["id"])

        list_response = self.client.get("/edges")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json(), [])

    def test_delete_missing_edge_returns_404(self) -> None:
        response = self.client.delete("/edges/999")
        self.assertEqual(response.status_code, 404)

    def test_self_referential_edge_is_rejected(self) -> None:
        node = self.client.post(
            "/nodes",
            json={"type": "idea", "raw_text": "Same", "source": "test"},
        ).json()
        response = self.client.post(
            "/edges",
            json={
                "from_node_id": node["id"],
                "to_node_id": node["id"],
                "type": "similar_to",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

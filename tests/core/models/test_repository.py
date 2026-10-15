import json

import pytest

from bilge.core.models.repository import (
    RepositoryFile,
    is_pinned_revision,
    is_safe_relative_path,
    is_valid_id,
    parse_tree,
    select,
    total_size,
)

LISTING = json.loads(
    '[{"type":"file","oid":"X1","size":42,"path":"onnx/tts.json"},'
    '{"type":"file","oid":"y","size":7,"path":"onnx/vocoder.onnx","lfs":{"oid":"ABC","size":7,"pointerSize":134}},'
    '{"type":"directory","oid":"z","size":0,"path":"onnx"},'
    '{"type":"file","oid":"w","size":5,"path":"README.md"},'
    '{"path":"broken"}]'
)


def test_decodes_the_hugging_face_tree_listing():
    files = parse_tree(LISTING)
    assert [f.path for f in files] == ["onnx/tts.json", "onnx/vocoder.onnx", "onnx", "README.md"]
    assert files[0].git_oid == "x1" and files[0].lfs_sha256 is None
    assert files[1].lfs_sha256 == "abc"
    assert total_size(files) == 54


def test_selects_by_pattern_and_drops_folders():
    assert [f.path for f in select(parse_tree(LISTING), ("onnx/*",))] == ["onnx/tts.json", "onnx/vocoder.onnx"]


def test_a_listing_that_is_not_a_list_gives_nothing():
    assert parse_tree({"error": "x"}) == []


@pytest.mark.parametrize(
    "path",
    [
        "../config.json",
        "/etc/config.json",
        "a/../../config.json",
        ".hidden/config.json",
        "a//config.json",
        "",
        "con fig.json",
    ],
)
def test_rejects_paths_that_could_leave_the_model_folder(path):
    assert not is_safe_relative_path(path)
    assert select([RepositoryFile(path, 1)], ("*",)) == []


def test_accepts_plain_nested_paths():
    assert is_safe_relative_path("tokenizer/tokenizer.json")


@pytest.mark.parametrize(
    ("repo_id", "valid"),
    [
        ("Supertone/supertonic-3", True),
        ("a/b/c", False),
        ("../x", False),
        ("owner/.git", False),
        ("owner", False),
        ("owner/na me", False),
    ],
)
def test_repository_ids_are_owner_slash_name(repo_id, valid):
    assert is_valid_id(repo_id) == valid


def test_revisions_must_be_full_commit_hashes():
    assert is_pinned_revision("a1" * 20)
    assert not is_pinned_revision("main")
    assert not is_pinned_revision("A1B2")


def test_rejects_negative_sizes_and_impossible_totals():
    assert select([RepositoryFile("config.json", -1)], ("*",)) == []
    assert total_size([RepositoryFile("a.json", -5)]) is None
    assert total_size([RepositoryFile("a.json", 2**63 - 1), RepositoryFile("b.json", 1)]) is None
    assert total_size([]) == 0

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dta_abrechnung.storage import LocalObjectStore


class LocalObjectStoreTest(unittest.TestCase):
    def test_put_and_get_blob_computes_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = LocalObjectStore(Path(tempdir))

            ref = store.put_blob(
                key="tenant-a/evidence/file.bin",
                content=b"payload",
                media_type="application/octet-stream",
                retention_class="regulated",
            )

            self.assertEqual(ref.size_bytes, 7)
            self.assertEqual(ref.checksum_sha256, "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5")
            self.assertEqual(store.get_blob(ref), b"payload")

    def test_immutable_store_rejects_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = LocalObjectStore(Path(tempdir), immutable=True)
            store.put_blob("tenant-a/object.txt", b"one", "text/plain", "regulated")

            with self.assertRaises(ValueError):
                store.put_blob("tenant-a/object.txt", b"two", "text/plain", "regulated")

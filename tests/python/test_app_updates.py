# SPDX-License-Identifier: Apache-2.0
"""Update policy regression tests: no network or real executable launch."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from python.spike_core import app_updates as updates


class Response(io.BytesIO):
    headers = {}


class UpdateTests(unittest.TestCase):
    def release(self, data=b"test setup"):
        return {"tag_name": "v0.4.0", "assets": [{"name": "SPIKE_0.4.0_x64-setup.exe", "size": len(data),
          "digest": "sha256:"+hashlib.sha256(data).hexdigest(),
          "browser_download_url": "https://github.com/wayri/spike/releases/download/v0.4.0/SPIKE_0.4.0_x64-setup.exe"}]}

    def test_version_comparison_and_platform(self):
        r=self.release()
        self.assertEqual(updates.select_release(r,"0.3.9","windows","x86_64")["status"],"available")
        self.assertEqual(updates.select_release(r,"0.5.0","windows","x86_64")["status"],"current")
        self.assertEqual(updates.select_release(r,"0.3.9","linux","x86_64")["status"],"unsupported")
        self.assertEqual(updates.select_release(r,"0.3.9","windows","aarch64")["status"],"unsupported")
        with self.assertRaises(ValueError): updates.version("0.4.0-beta.1")

    def test_missing_hash_and_duplicate_asset_fail_closed(self):
        r=self.release();r["assets"][0].pop("digest")
        self.assertEqual(updates.select_release(r,"0.3.9","windows","x86_64")["status"],"unsupported")
        r=self.release();r["assets"]*=2
        self.assertEqual(updates.select_release(r,"0.3.9","windows","x86_64")["status"],"unsupported")

    def test_transport_boundaries(self):
        for url in ["http://github.com/wayri/spike/releases/download/x/a.exe",
          "https://github.com.evil.test/wayri/spike/releases/download/x/a.exe",
          "https://user@github.com/wayri/spike/releases/download/x/a.exe",
          "https://github.com/other/repo/releases/download/x/a.exe",
          "https://github.com/wayri/spike/releases/download/%2e%2e/a.exe",
          "file:///setup.exe", "https://release-assets.githubusercontent.com/other/a.exe"]:
            with self.subTest(url=url),self.assertRaises(ValueError): updates.validate_url(url,redirect=True)
        updates.validate_url("https://release-assets.githubusercontent.com/github-production-release-asset/123/abc?token=1",redirect=True)

    def test_download_integrity_and_atomic_publish(self):
        result=updates.select_release(self.release(),"0.3.9","windows","x86_64")
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,"cache_root",return_value=Path(folder)),patch.object(updates,"check",return_value=result):
            with patch.object(updates,"open_url",return_value=Response(b"bad")):
                with self.assertRaises(ValueError):updates.download({"latest_version":"0.4.0"},lambda _:None)
            self.assertFalse((Path(folder)/"setup.exe").exists())
            self.assertFalse((Path(folder)/"setup.partial").exists())
            frames=[]
            with patch.object(updates,"open_url",return_value=Response(b"test setup")):
                self.assertEqual(updates.download({"latest_version":"0.4.0"},frames.append)["status"],"ready")
            self.assertEqual((Path(folder)/"setup.exe").read_bytes(),b"test setup")
            self.assertEqual(frames[-1]["received_bytes"],10)

    def test_changed_release_and_existing_file_are_not_overwritten(self):
        result=updates.select_release(self.release(),"0.3.9","windows","x86_64")
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,"cache_root",return_value=Path(folder)),patch.object(updates,"check",return_value=result):
            p=Path(folder)/"setup.exe";p.write_bytes(b"existing")
            with self.assertRaises(ValueError):updates.download({"latest_version":"0.3.9"},lambda _:None)
            with self.assertRaises(ValueError):updates.download({"latest_version":"0.4.0"},lambda _:None)
            self.assertEqual(p.read_bytes(),b"existing")

    def test_cache_owner_and_sibling_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"LOCALAPPDATA":folder}):
            root=updates.cache_root();self.assertEqual((root/"owner.txt").read_text(),updates.MARKER)
            (root/"owner.txt").write_text("user data")
            with self.assertRaises(ValueError):updates.cache_root()
            self.assertEqual((root/"owner.txt").read_text(),"user data")

    def test_oversized_and_prerelease_metadata(self):
        r=self.release();r["prerelease"]=True
        with self.assertRaises(ValueError):updates.select_release(r,"0.3.9","windows","x86_64")
        r=self.release();r["assets"][0]["size"]=updates.MAX_SIZE+1
        with self.assertRaises(ValueError):updates.select_release(r,"0.3.9","windows","x86_64")


if __name__=="__main__":unittest.main()

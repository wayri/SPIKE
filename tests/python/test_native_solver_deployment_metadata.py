import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class NativeSolverDeploymentMetadataTests(unittest.TestCase):
    def test_lockfile_requires_a_detached_signature_and_external_petsc_mumps(self):
        lockfile = json.loads((ROOT / "dependencies.lock.json").read_text(encoding="utf-8"))

        self.assertEqual(lockfile["signature"]["format"], "cms-detached-sha256")
        self.assertTrue(lockfile["signature"]["required"])
        petsc_mumps = next(item for item in lockfile["dependencies"] if item["id"] == "petsc-mumps")
        self.assertIn("never downloaded by SPIKE", petsc_mumps["source"])

    def test_installer_requires_signed_readiness_and_stages_signed_activation(self):
        installer = (ROOT / "scripts" / "install_sparselizard_native.ps1").read_text(encoding="utf-8")

        self.assertIn("[Parameter(Mandatory)][string]$TrustCertificatePath", installer)
        self.assertIn('[Parameter(ParameterSetName = "Install", Mandatory)][string]$PetscMumpsReadinessPath', installer)
        self.assertIn("spike/petsc-mumps-readiness/v1", installer)
        self.assertIn("matsolvermumps_registered", installer)
        self.assertIn("spike/sparselizard-native-runtime/v2", installer)
        self.assertIn("Activate-Bundle", installer)
        self.assertIn("[switch]$Rollback", installer)
        self.assertNotIn('"mingw-w64-ucrt-x86_64-petsc"', installer)
        self.assertNotIn('"mingw-w64-ucrt-x86_64-mumps"', installer)

    def test_registration_script_is_cross_platform_and_requires_functional_mumps_evidence(self):
        registration = (ROOT / "scripts" / "register_petsc_mumps_readiness.ps1").read_text(encoding="utf-8")

        self.assertIn('ValidateSet("windows-ucrt64", "linux-x86_64")', registration)
        self.assertIn("spike/petsc-mumps-dependency/v1", registration)
        self.assertIn("spike/petsc-mumps-probe/v1", registration)
        self.assertIn("MATSOLVERMUMPS", registration)
        self.assertIn("solve_verified", registration)
        self.assertNotIn("Invoke-WebRequest", registration)
        self.assertNotIn("pacman", registration)

    def test_deployment_docs_do_not_present_petsc_mumps_as_installed(self):
        deployment = (ROOT / "docs" / "EXTERNAL_SOLVER_DEPLOYMENT.md").read_text(encoding="utf-8")
        native = (ROOT / "docs" / "SPARSELIZARD_NATIVE_WINDOWS.md").read_text(encoding="utf-8")

        self.assertIn("SPIKE never downloads PETSc or MUMPS", deployment)
        self.assertIn("Not asserted by SPIKE", deployment)
        self.assertIn("SPIKE does not download or install them", native)
        self.assertIn("-Rollback", native)


if __name__ == "__main__":
    unittest.main()

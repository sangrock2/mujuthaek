import importlib.util
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


aws_module = module("aws_personal")
packager = module("package_release")


class DeploymentGuards(unittest.TestCase):
    def test_wrong_account_cannot_reach_plan_or_mutation(self):
        aws = aws_module.AWS("personal-example", "123456789012")
        calls = []

        def call(*args, **kwargs):
            calls.append(args)
            return {"Account": "999999999999"}

        aws.call = call
        with self.assertRaises(RuntimeError):
            aws.verify()
        self.assertEqual(calls, [("sts", "get-caller-identity")])

    def test_unselected_and_old_profiles_are_rejected(self):
        for profile in ["", "default", "iter-local", "mujuthaek-s3"]:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                aws_module.AWS(profile, "123456789012")

    def test_archive_never_includes_local_credentials_or_generated_files(self):
        for name in ["frontend/.env.local", "backend/services/api/.env", "frontend/server.pem",
                     "backend/infra/deploy/personal/runtime/ssh-key", "frontend/node_modules/a.js",
                     "../frontend/package.json"]:
            with self.subTest(name=name):
                self.assertFalse(packager.allowed(name))
        self.assertTrue(packager.allowed("frontend/Dockerfile"))
        self.assertTrue(packager.allowed("backend/services/api/src/main/resources/application.yml"))

    def test_changed_price_fails_closed(self):
        aws = aws_module.AWS("personal-example", "123456789012")
        aws.call = lambda *a, **kw: {"bundles": [{"bundleId": aws_module.BUNDLE_ID, "isActive": True,
                                                  "ramSizeInGb": aws_module.BUNDLE_RAM, "price": aws_module.BUNDLE_MAX_PRICE + 1,
                                                  "supportedPlatforms": ["LINUX_UNIX"]}]}
        with self.assertRaises(RuntimeError):
            aws.bundle()

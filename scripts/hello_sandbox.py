"""First Token Factory Sandbox run. Needs NEBIUS_API_KEY + NEBIUS_PROJECT_ID in .env:

    python -m scripts.hello_sandbox

Lists available images, imports python:3.12-slim (first run only), then runs
a one-liner inside the sandbox and prints stdout / stderr / exit code.
"""
from contree_sdk import ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig

from agent.config import settings

PYTHON_IMAGE = "docker://docker.io/library/python:3.12-slim"


def main():
    if not settings.project_id:
        raise RuntimeError("NEBIUS_PROJECT_ID is not set. Copy your project ID from the Token Factory console into .env.")
    auth = IAMAuth(token=settings.api_key, project_id=settings.project_id, base_url=settings.contree_url)
    sdk = ContreeSync(ContreeConfig(auth=auth))

    images = sdk.images()
    print(f"IMAGES ({len(images)}):", [img.tag or str(img.uuid) for img in images][:10])

    image = sdk.images.oci(PYTHON_IMAGE)  # returns the existing image if already imported
    print("USING:", image)

    result = image.run(shell="python -c 'import sys; print(1 + 1, sys.version)'").wait()
    print("\nSTDOUT:", result.stdout)
    print("STDERR:", result.stderr or "(none)")
    print("EXIT CODE:", result.exit_code)


if __name__ == "__main__":
    main()

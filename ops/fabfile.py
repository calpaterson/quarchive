from fabric import task


@task
def deploy(c, version):
    package_name = f"quarchive-{version}-py3-none-any.whl"
    github_url = (
        f"https://github.com/calpaterson/quarchive/releases"
        f"/download/server-v{version}/quarchive-{version}-py3-none-any.whl"
    )
    c.run("rm *.whl")
    with c.prefix("source quarchive-venv/bin/activate"):
        c.run(f"wget {github_url}")
        c.run(f"pip install {package_name}")
    c.sudo("systemctl restart quarchive-web")
    c.sudo("systemctl restart quarchive-celery")

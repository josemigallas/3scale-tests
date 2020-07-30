"""
Test if url rewriting policy works with APIAP
https://issues.redhat.com/browse/THREESCALE-4301
"""
import pytest
from packaging.version import Version  # noqa # pylint: disable=unused-import

from testsuite import rawobj, TESTED_VERSION  # noqa # pylint: disable=unused-import

# TODO: Remove pylint disable when pytest fixes problem, probably in 6.0.1
# https://github.com/pytest-dev/pytest/pull/7565
# pylint: disable=not-callable
pytestmark = pytest.mark.skipif("TESTED_VERSION < Version('2.8')")


@pytest.fixture(scope="module")
def backends_mapping(custom_backend):
    """
    Create custom backend with path "/bin"
    """
    return {"/bin": custom_backend("backend")}


@pytest.fixture(scope="module")
def policy_settings():
    """
    Add url rewriting policy configured to rewrite "/v1/" to "/v5/"
    """
    return rawobj.PolicyConfig("url_rewriting", {"commands": [{"op": "sub", "regex": "/v1/", "replace": "/v5/"}]})


@pytest.fixture(scope="module")
def apicast_first():
    """
    Have url_rewriting in the policy chain after the apicast

    This is default setup. BEWARE fixture order does matter here!
    """


@pytest.fixture(scope="module")
def url_rewriting_first(service):
    """
    Have url_rewriting in the policy chain before the apicast

    Let's revert the chain. BEWARE fixture order does matter here!
    """

    proxy = service.proxy.list()

    policy_chain = proxy.policies.list()
    policy_chain["policies_config"].reverse()
    policy_chain.update()

    proxy.update()


# TODO: Remove pylint disable when pytest fixes problem, probably in 6.0.1
# https://github.com/pytest-dev/pytest/pull/7565
# pylint: disable=not-callable
@pytest.mark.parametrize("setup", ("apicast_first", "url_rewriting_first"))
def test(request, api_client, setup):
    """Test that url_rewriting works with APIAP as expected

    url_rewriting has to work in same way like before APIAP doesn't whether
    url_rewriting is put before or after apicast
    """

    request.getfixturevalue(setup)

    response = api_client.get("/bin/anything/v2/test")
    assert response.status_code == 200
    assert response.json()["path"] == "/anything/v2/test"

    response = api_client.get("/bin/anything/v1/test")
    assert response.status_code == 200
    assert response.json()["path"] == "/anything/v5/test"

"""
Test that content caching policy is working correctly with env:
    - APICAST_CACHE_STATUS_CODES = status code which should be cached
    - APICAST_CACHE_MAX_TIME = max time that content can be cached
"""
import time
from packaging.version import Version  # noqa # pylint: disable=unused-import

import pytest

from testsuite import rawobj, TESTED_VERSION  # noqa # pylint: disable=unused-import
from testsuite.echoed_request import EchoedRequest
from testsuite.gateways.gateways import Capability
from testsuite.utils import blame, randomize

# TODO: Remove pylint disable when pytest fixes problem, probably in 6.0.1
# https://github.com/pytest-dev/pytest/pull/7565
# pylint: disable=not-callable
pytestmark = [pytest.mark.skipif("TESTED_VERSION < Version('2.9')"),
              pytest.mark.required_capabilities(Capability.APICAST, Capability.CUSTOM_ENVIRONMENT)]


@pytest.fixture(scope="module")
def gateway_environment(gateway_environment):
    """Enable caching on gateway"""
    gateway_environment.update({"APICAST_CACHE_STATUS_CODES": "200",
                                "APICAST_CACHE_MAX_TIME": "30s"})
    return gateway_environment


@pytest.fixture(scope="module")
def policy_settings():
    """content caching policy configuration"""
    return rawobj.PolicyConfig("content_caching", {
        "rules": [{
            "cache": True,
            "header": "X-Cache-Status",
            "condition": {
                "combine_op": "and",
                "operations": [{
                    "left": "ooo",
                    "op": "==",
                    "right": "ooo"
                }]
            }
        }]
    })


@pytest.fixture(scope="module")
def backends_mapping(custom_backend, private_base_url, lifecycle_hooks):
    """
    Create 2 separate backends:
        - path to Backend 1: "/echo-api"
        - path to Backend 2: "/httpbin"
    """
    return {"/echo-api": custom_backend("backend_one", endpoint=private_base_url("echo_api"), hooks=lifecycle_hooks),
            "/httpbin": custom_backend("backend_two", endpoint=private_base_url("httpbin_go"), hooks=lifecycle_hooks)}


@pytest.fixture(scope="module")
def service(service, policy_settings):
    """Add policy to the first service"""
    service.proxy.list().policies.append(policy_settings)
    return service


# pylint: disable=too-many-arguments
@pytest.fixture(scope="module")
def service2(custom_service, backends_mapping, request, service_proxy_settings, policy_settings, lifecycle_hooks):
    """Second service"""
    service = custom_service({"name": blame(request, "svc")}, service_proxy_settings, backends_mapping,
                             hooks=lifecycle_hooks)
    service.proxy.list().policies.append(policy_settings)
    return service


@pytest.fixture(scope="module")
def application2(service2, custom_application, custom_app_plan, lifecycle_hooks):
    """Second application to test with"""
    plan = custom_app_plan(rawobj.ApplicationPlan(randomize("AppPlan")), service2)
    return custom_application(rawobj.Application(randomize("App"), plan), hooks=lifecycle_hooks)


@pytest.fixture(scope="module")
def api_client(api_client):
    """
    Api client for the first service
    Apicast needs to load configuration in order to cache incomming requests
    """
    api_client.get("/echo-api/")
    return api_client


@pytest.fixture(scope="module")
def api_client2(application2):
    """
    Api client for the second service
    Apicast needs to load configuration in order to cache incoming requests
    """
    client = application2.api_client()
    client.get("/echo-api/")
    return client


def test_wont_cache(api_client, private_base_url):
    """Test that redirected request (302 status code) will not be cached"""
    payload = {'url': private_base_url("echo_api")}
    response = api_client.get("/httpbin/redirect-to", params=payload, headers=dict(origin="localhost"))
    # First request was redirected
    assert response.history[0].status_code == 302
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") != "HIT"
    echoed_request = EchoedRequest.create(response)

    # wont cache redirect request
    response = api_client.get("/httpbin/redirect-to", params=payload, headers=dict(origin="localhost"))
    # First request was redirected
    assert response.history[0].status_code == 302
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") != "HIT"
    echoed_request2 = EchoedRequest.create(response)

    # body wasn't cached
    assert echoed_request.json['uuid'] != echoed_request2.json['uuid']


def test_will_cache(api_client, api_client2):
    """
    Test that requests will be cached with status code 200 and the cache will expire after 30 seconds
    """
    response = api_client.get("/echo-api/testing", headers=dict(origin="localhost"))
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") != "HIT"
    echoed_request = EchoedRequest.create(response)

    response = api_client.get("/echo-api/testing", headers=dict(origin="localhost"))
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") == "HIT"
    echoed_request_cached = EchoedRequest.create(response)

    # body was cached
    assert echoed_request.json['uuid'] == echoed_request_cached.json['uuid']

    # another service wont hit the cache with the same request
    response = api_client2.get("/echo-api/testing", headers=dict(origin="localhost"))
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") != "HIT"

    echoed_request_not_cached = EchoedRequest.create(response)
    assert echoed_request.json['uuid'] != echoed_request_not_cached.json['uuid']

    # Timeout is set to 30, so this should be safe
    time.sleep(40)

    # request expired
    response = api_client.get("/echo-api/testing", headers=dict(origin="localhost"))
    assert response.status_code == 200
    assert response.headers.get("X-Cache-Status") == "EXPIRED"
    echoed_request_new = EchoedRequest.create(response)

    assert echoed_request.json['uuid'] != echoed_request_new.json['uuid']

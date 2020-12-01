from datetime import datetime
import json
from unittest.mock import patch
import httpretty
import pytest

from freshbooks import Client as FreshBooksClient
from freshbooks import FreshBooksError
from freshbooks.api.accounting import AccountingResource
from freshbooks.api.projects import ProjectsResource
from freshbooks.api.resource import HttpVerbs
from freshbooks.client import API_BASE_URL
from freshbooks.errors import FreshBooksNotImplementedError
from tests import get_fixture


class TestClientAuth:
    def setup_method(self, method):
        self.freshBooksClient = FreshBooksClient(client_id="some_client", redirect_uri="https://example.com")

    def test_get_auth_request_url(self):
        auth_url = self.freshBooksClient.get_auth_request_url()
        assert (
            auth_url == "https://auth.freshbooks.com/service/auth/oauth/authorize?"
            "client_id=some_client&response_type=code&redirect_uri=https%3A%2F%2Fexample.com"
        )

    def test_get_auth_request_url__with_scopes(self):
        scopes = ["some:scope", "another:scope"]
        auth_url = self.freshBooksClient.get_auth_request_url(scopes)
        assert (
            auth_url == "https://auth.freshbooks.com/service/auth/oauth/authorize?"
            "client_id=some_client&response_type=code&redirect_uri=https%3A%2F%2Fexample.com"
            "&scope=some%3Ascope+another%3Ascope"
        )

    @httpretty.activate
    def test_get_access_token(self):
        url = "{}/auth/oauth/token".format(API_BASE_URL)
        httpretty.register_uri(
            httpretty.POST,
            url,
            body=json.dumps(get_fixture("auth_token_response")),
            status=200
        )

        result = self.freshBooksClient.get_access_token("some_grant")

        assert httpretty.last_request().body == (
            "client_id=some_client&grant_type=authorization_code"
            "&redirect_uri=https%3A%2F%2Fexample.com&code=some_grant").encode("utf-8")
        assert self.freshBooksClient.access_token == "my_access_token"
        assert result.access_token == "my_access_token"
        assert self.freshBooksClient.refresh_token == "my_refresh_token"
        assert result.refresh_token == "my_refresh_token"
        assert self.freshBooksClient.access_token_expires_at == datetime(2010, 10, 17)
        assert result.access_token_expires_at == datetime(2010, 10, 17)

    @httpretty.activate
    def test_get_access_token__failure(self):
        url = "{}/auth/oauth/token".format(API_BASE_URL)
        httpretty.register_uri(httpretty.POST, url, status=500)

        try:
            self.freshBooksClient.get_access_token("some_grant")
        except FreshBooksError as e:
            assert str(e) == "Failed to fetch access_token"
            assert e.status_code == 500

    @httpretty.activate
    def test_get_refresh_token(self):
        self.freshBooksClient = FreshBooksClient(
            client_id="some_client",
            redirect_uri="https://example.com",
            access_token="an_old_token",
            refresh_token="an_old_refresh_token"
        )
        url = "{}/auth/oauth/token".format(API_BASE_URL)
        httpretty.register_uri(
            httpretty.POST,
            url,
            body=json.dumps(get_fixture("auth_token_response")),
            status=200
        )

        result = self.freshBooksClient.refresh_access_token()

        assert httpretty.last_request().body == (
            "client_id=some_client&grant_type=refresh_token"
            "&redirect_uri=https%3A%2F%2Fexample.com&refresh_token=an_old_refresh_token").encode("utf-8")
        assert self.freshBooksClient.access_token == "my_access_token"
        assert result.access_token == "my_access_token"
        assert self.freshBooksClient.refresh_token == "my_refresh_token"
        assert result.refresh_token == "my_refresh_token"
        assert self.freshBooksClient.access_token_expires_at == datetime(2010, 10, 17)
        assert result.access_token_expires_at == datetime(2010, 10, 17)

    @httpretty.activate
    def test_get_refresh_token__uninitialized_client(self):
        url = "{}/auth/oauth/token".format(API_BASE_URL)
        httpretty.register_uri(
            httpretty.POST,
            url,
            body=json.dumps(get_fixture("auth_token_response")),
            status=200
        )

        result = self.freshBooksClient.refresh_access_token("an_old_refresh_token")

        assert httpretty.last_request().body == (
            "client_id=some_client&grant_type=refresh_token"
            "&redirect_uri=https%3A%2F%2Fexample.com&refresh_token=an_old_refresh_token").encode("utf-8")
        assert self.freshBooksClient.access_token == "my_access_token"
        assert result.access_token == "my_access_token"
        assert self.freshBooksClient.refresh_token == "my_refresh_token"
        assert result.refresh_token == "my_refresh_token"
        assert self.freshBooksClient.access_token_expires_at == datetime(2010, 10, 17)
        assert result.access_token_expires_at == datetime(2010, 10, 17)


class TestClientResources:
    def setup_method(self, method):
        self.freshBooksClient = FreshBooksClient(client_id="some_client", redirect_uri="https://example.com")

    @pytest.mark.parametrize(
        "resource_name, single_name, delete_via_update",
        [
            ("clients", "client", True),
            ("invoices", "invoice", False),
            ("expenses", "expense", True),
            ("taxes", "tax", False)
        ]
    )
    @patch.object(AccountingResource, "_get_url", return_value="some_url")
    def test_accounting_resource_methods(self, mock_url, resource_name, single_name, delete_via_update):
        """Test general methods on accounting resources"""
        account_id = 1234
        resource_id = 2345
        resource_ = getattr(self.freshBooksClient, resource_name)

        list_response = {resource_name: [], "page": 1, "pages": 0, "per_page": 15, "total": 0}
        single_response = {single_name: {}}

        with patch.object(AccountingResource, "_request", return_value=list_response) as mock_request:
            resource_.list(account_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

        with patch.object(AccountingResource, "_request", return_value=single_response) as mock_request:
            resource_.get(account_id, resource_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

            resource_.create(account_id, {})
            mock_request.assert_called_with("some_url", HttpVerbs.POST, data={single_name: {}})

            resource_.update(account_id, resource_id, {})
            mock_request.assert_called_with("some_url", HttpVerbs.PUT, data={single_name: {}})

            resource_.delete(account_id, resource_id)
            if delete_via_update:
                mock_request.assert_called_with("some_url", HttpVerbs.PUT, data={single_name: {"vis_state": 1}})
            else:
                mock_request.assert_called_with("some_url", HttpVerbs.DELETE)

    @pytest.mark.parametrize(
        "resource_name, single_name",
        [
            ("projects", "project")
        ]
    )
    @patch.object(ProjectsResource, "_get_url", return_value="some_url")
    def test_project_resource_methods(self, mock_url, resource_name, single_name):
        """Test general methods on project resources"""
        business_id = 1234
        resource_id = 2345
        resource_ = getattr(self.freshBooksClient, resource_name)

        list_response = {resource_name: [], "meta": {"page": 1, "pages": 0, "per_page": 15, "total": 0}}
        single_response = {single_name: {}}

        with patch.object(ProjectsResource, "_request", return_value=list_response) as mock_request:
            resource_.list(business_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

        with patch.object(ProjectsResource, "_request", return_value=single_response) as mock_request:
            resource_.get(business_id, resource_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

            resource_.create(business_id, {})
            mock_request.assert_called_with("some_url", HttpVerbs.POST, data={single_name: {}})

            resource_.update(business_id, resource_id, {})
            mock_request.assert_called_with("some_url", HttpVerbs.PUT, data={single_name: {}})

            resource_.delete(business_id, resource_id)
            mock_request.assert_called_with("some_url", HttpVerbs.DELETE)

    @patch.object(AccountingResource, "_get_url", return_value="some_url")
    def test_accounting_staffs_resource_methods(self, mock_url):
        """Test methods on accounting staff resource, which has no create"""
        account_id = 1234
        resource_id = 2345
        resource_name = "staffs"
        single_name = "staff"
        resource_ = getattr(self.freshBooksClient, resource_name)

        list_response = {resource_name: [], "page": 1, "pages": 0, "per_page": 15, "total": 0}
        single_response = {single_name: {}}

        with patch.object(AccountingResource, "_request", return_value=list_response) as mock_request:
            resource_.list(account_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

        with patch.object(AccountingResource, "_request", return_value=single_response) as mock_request:
            resource_.get(account_id, resource_id)
            mock_request.assert_called_with("some_url", HttpVerbs.GET)

            with pytest.raises(FreshBooksNotImplementedError):
                resource_.create(account_id, {})

            resource_.update(account_id, resource_id, {})
            mock_request.assert_called_with("some_url", HttpVerbs.PUT, data={single_name: {}})

            resource_.delete(account_id, resource_id)
            mock_request.assert_called_with("some_url", HttpVerbs.PUT, data={single_name: {"vis_state": 1}})
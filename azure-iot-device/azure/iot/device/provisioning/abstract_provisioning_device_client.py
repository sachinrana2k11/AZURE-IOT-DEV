# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""
This module provides an abstract interface representing clients which can communicate with the
Device Provisioning Service.
"""

import abc
import logging
from azure.iot.device.provisioning import pipeline

from azure.iot.device.common.auth import sastoken as st
from azure.iot.device.common import auth, handle_exceptions

logger = logging.getLogger(__name__)


def _validate_kwargs(exclude=[], **kwargs):
    """Helper function to validate user provided kwargs.
    Raises TypeError if an invalid option has been provided"""
    # TODO: add support for server_verification_cert
    valid_kwargs = [
        "server_verification_cert",
        "gateway_hostname",
        "websockets",
        "cipher",
        "proxy_options",
        "sastoken_ttl",
        "keep_alive",
    ]

    for kwarg in kwargs:
        if (kwarg not in valid_kwargs) or (kwarg in exclude):
            raise TypeError("Unsupported keyword argument '{}'".format(kwarg))


def validate_registration_id(reg_id):
    if not (reg_id and reg_id.strip()):
        raise ValueError("Registration Id can not be none, empty or blank.")


def _get_config_kwargs(**kwargs):
    """Get the subset of kwargs which pertain the config object"""
    valid_config_kwargs = [
        "server_verification_cert",
        "gateway_hostname",
        "websockets",
        "cipher",
        "proxy_options",
        "keep_alive",
    ]

    config_kwargs = {}
    for kwarg in kwargs:
        if kwarg in valid_config_kwargs:
            config_kwargs[kwarg] = kwargs[kwarg]
    return config_kwargs


def _form_sas_uri(id_scope, registration_id):
    return "{id_scope}/registrations/{registration_id}".format(
        id_scope=id_scope, registration_id=registration_id
    )


class AbstractProvisioningDeviceClient(abc.ABC):
    """
    Super class for any client that can be used to register devices to Device Provisioning Service.
    """

    def __init__(self, pipeline):
        """
        Initializes the provisioning client.

        NOTE: This initializer should not be called directly.
        Instead, the class methods that start with `create_from_` should be used to create a
        client object.

        :param pipeline: Instance of the provisioning pipeline object.
        :type pipeline: :class:`azure.iot.device.provisioning.pipeline.MQTTPipeline`
        """
        self._pipeline = pipeline
        self._provisioning_payload = None
        self._client_csr = None

        self._pipeline.on_background_exception = handle_exceptions.handle_background_exception

    @classmethod
    def create_from_symmetric_key(
        cls, provisioning_host, registration_id, id_scope, symmetric_key, **kwargs
    ):
        """
        Create a client which can be used to run the registration of a device with provisioning service
        using Symmetric Key authentication.

        :param str provisioning_host: Host running the Device Provisioning Service.
            Can be found in the Azure portal in the Overview tab as the string Global device endpoint.
        :param str registration_id: The registration ID used to uniquely identify a device in the
            Device Provisioning Service. The registration ID is alphanumeric, lowercase string
            and may contain hyphens.
        :param str id_scope: The ID scope used to uniquely identify the specific provisioning
            service the device will register through. The ID scope is assigned to a
            Device Provisioning Service when it is created by the user and is generated by the
            service and is immutable, guaranteeing uniqueness.
        :param str symmetric_key: The key which will be used to create the shared access signature
            token to authenticate the device with the Device Provisioning Service. By default,
            the Device Provisioning Service creates new symmetric keys with a default length of
            32 bytes when new enrollments are saved with the Auto-generate keys option enabled.
            Users can provide their own symmetric keys for enrollments by disabling this option
            within 16 bytes and 64 bytes and in valid Base64 format.

        :param str server_verification_cert: Configuration Option. The trusted certificate chain.
            Necessary when using connecting to an endpoint which has a non-standard root of trust,
            such as a protocol gateway.
        :param str gateway_hostname: Configuration Option. The gateway hostname for the gateway
            device.
        :param bool websockets: Configuration Option. Default is False. Set to true if using MQTT
            over websockets.
        :param cipher: Configuration Option. Cipher suite(s) for TLS/SSL, as a string in
            "OpenSSL cipher list format" or as a list of cipher suite strings.
        :type cipher: str or list(str)
        :param proxy_options: Options for sending traffic through proxy servers.
        :type proxy_options: :class:`azure.iot.device.ProxyOptions`
        :param int keepalive: Maximum period in seconds between communications with the
            broker. If no other messages are being exchanged, this controls the
            rate at which the client will send ping messages to the broker.
            If not provided default value of 60 secs will be used.
        :raises: TypeError if given an unrecognized parameter.

        :returns: A ProvisioningDeviceClient instance which can register via Symmetric Key.
        """
        validate_registration_id(registration_id)
        # Ensure no invalid kwargs were passed by the user
        _validate_kwargs(**kwargs)

        # Create SasToken
        uri = _form_sas_uri(id_scope=id_scope, registration_id=registration_id)
        signing_mechanism = auth.SymmetricKeySigningMechanism(key=symmetric_key)
        token_ttl = kwargs.get("sastoken_ttl", 3600)
        try:
            sastoken = st.RenewableSasToken(uri, signing_mechanism, ttl=token_ttl)
        except st.SasTokenError as e:
            new_err = ValueError("Could not create a SasToken using the provided values")
            new_err.__cause__ = e
            raise new_err

        # Pipeline Config setup
        config_kwargs = _get_config_kwargs(**kwargs)
        pipeline_configuration = pipeline.ProvisioningPipelineConfig(
            hostname=provisioning_host,
            registration_id=registration_id,
            id_scope=id_scope,
            sastoken=sastoken,
            **config_kwargs
        )

        # Pipeline setup
        mqtt_provisioning_pipeline = pipeline.MQTTPipeline(pipeline_configuration)

        return cls(mqtt_provisioning_pipeline)

    @classmethod
    def create_from_x509_certificate(
        cls, provisioning_host, registration_id, id_scope, x509, **kwargs
    ):
        """
        Create a client which can be used to run the registration of a device with
        provisioning service using X509 certificate authentication.

        :param str provisioning_host: Host running the Device Provisioning Service. Can be found in
            the Azure portal in the Overview tab as the string Global device endpoint.
        :param str registration_id: The registration ID used to uniquely identify a device in the
            Device Provisioning Service. The registration ID is alphanumeric, lowercase string
            and may contain hyphens.
        :param str id_scope: The ID scope is used to uniquely identify the specific
            provisioning service the device will register through. The ID scope is assigned to a
            Device Provisioning Service when it is created by the user and is generated by the
            service and is immutable, guaranteeing uniqueness.
        :param x509: The x509 certificate, To use the certificate the enrollment object needs to
            contain cert (either the root certificate or one of the intermediate CA certificates).
            If the cert comes from a CER file, it needs to be base64 encoded.
        :type x509: :class:`azure.iot.device.X509`

        :param str server_verification_cert: Configuration Option. The trusted certificate chain.
            Necessary when using connecting to an endpoint which has a non-standard root of trust,
            such as a protocol gateway.
        :param str gateway_hostname: Configuration Option. The gateway hostname for the gateway
            device.
        :param bool websockets: Configuration Option. Default is False. Set to true if using MQTT
            over websockets.
        :param cipher: Configuration Option. Cipher suite(s) for TLS/SSL, as a string in
            "OpenSSL cipher list format" or as a list of cipher suite strings.
        :type cipher: str or list(str)
        :param proxy_options: Options for sending traffic through proxy servers.
        :type proxy_options: :class:`azure.iot.device.ProxyOptions`
        :param int keepalive: Maximum period in seconds between communications with the
            broker. If no other messages are being exchanged, this controls the
            rate at which the client will send ping messages to the broker.
            If not provided default value of 60 secs will be used.
        :raises: TypeError if given an unrecognized parameter.

        :returns: A ProvisioningDeviceClient which can register via X509 client certificates.
        """
        validate_registration_id(registration_id)
        # Ensure no invalid kwargs were passed by the user
        excluded_kwargs = ["sastoken_ttl"]
        _validate_kwargs(exclude=excluded_kwargs, **kwargs)

        # Pipeline Config setup
        config_kwargs = _get_config_kwargs(**kwargs)
        pipeline_configuration = pipeline.ProvisioningPipelineConfig(
            hostname=provisioning_host,
            registration_id=registration_id,
            id_scope=id_scope,
            x509=x509,
            **config_kwargs
        )

        # Pipeline setup
        mqtt_provisioning_pipeline = pipeline.MQTTPipeline(pipeline_configuration)

        return cls(mqtt_provisioning_pipeline)

    @abc.abstractmethod
    def register(self):
        """
        Register the device with the Device Provisioning Service.
        """
        pass

    @property
    def provisioning_payload(self):
        return self._provisioning_payload

    @provisioning_payload.setter
    def provisioning_payload(self, provisioning_payload):
        """
        Set the payload that will form the request payload in a registration request.

        :param provisioning_payload: The payload that can be supplied by the user.
        :type provisioning_payload: This can be an object or dictionary or a string or an integer.
        """
        self._provisioning_payload = provisioning_payload

    @property
    def client_csr(self):
        return self._client_csr

    @client_csr.setter
    def client_csr(self, csr):
        """
        Set the certificate signing request for device client certificate.
        The certificate will be used later for authentication after provisioning.
        :param csr: The certificate signing request
        """
        self._client_csr = csr


def log_on_register_complete(result=None):
    # This could be a failed/successful registration result from DPS
    # or a error from polling machine. Response should be given appropriately
    if result is not None:
        if result.status == "assigned":
            logger.info("Successfully registered with Provisioning Service")
        else:  # There be other statuses
            logger.info("Failed registering with Provisioning Service")

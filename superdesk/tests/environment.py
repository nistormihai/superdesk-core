# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import os
from flask import json

from apps.io.tests import setup_providers, teardown_providers
from superdesk import tests
from superdesk.factory.app import get_app
from superdesk.tests import setup_auth_user
from superdesk.vocabularies.command import VocabulariesPopulateCommand
from superdesk.tests.mocks import TestSearchProvider
from superdesk.tests.steps import get_macro_path


readonly_fields = ['display_name', 'password', 'phone', 'first_name', 'last_name']
LDAP_SERVER = os.environ.get('LDAP_SERVER')


def setup_before_all(context, config, app_factory):
    """
    Keep it for backwards compatibility.

    TODO: it needs to be cleaned on each superdesk repo.
    """
    setup_before_all.config = config
    setup_before_all.app_factory = app_factory


def setup_before_scenario(context, scenario, config, app_factory):
    if scenario.status != 'skipped' and 'notesting' in scenario.tags:
        config['SUPERDESK_TESTING'] = False

    tests.setup(context, config, app_factory, bool(config))

    context.headers = [
        ('Content-Type', 'application/json'),
        ('Origin', 'localhost')
    ]

    if 'dbauth' in scenario.tags and LDAP_SERVER:
        scenario.mark_skipped()

    if 'ldapauth' in scenario.tags and not LDAP_SERVER:
        scenario.mark_skipped()

    if 'alchemy' in scenario.tags and not context.app.config.get('KEYWORDS_KEY_API'):
        scenario.mark_skipped()

    if 'clean_snapshots' in scenario.tags:
        tests.use_snapshot.cache.clear()

    setup_search_provider(context.app)

    if scenario.status != 'skipped' and 'auth' in scenario.tags:
        setup_auth_user(context)

    if scenario.status != 'skipped' and 'provider' in scenario.tags:
        setup_providers(context)

    if scenario.status != 'skipped' and 'vocabulary' in scenario.tags:
        with context.app.app_context():
            cmd = VocabulariesPopulateCommand()
            filename = os.path.join(os.path.abspath(os.path.dirname("features/steps/fixtures/")), "vocabularies.json")
            cmd.run(filename)

    if scenario.status != 'skipped' and 'content_type' in scenario.tags:
        with context.app.app_context():
            cmd = VocabulariesPopulateCommand()
            filename = os.path.join(os.path.abspath(os.path.dirname("features/steps/fixtures/")), "content_types.json")
            cmd.run(filename)

    if scenario.status != 'skipped' and 'notification' in scenario.tags:
        tests.setup_notification(context)


def before_all(context):
    # https://pythonhosted.org/behave/api.html#logging-setup
    context.config.setup_logging()


def before_feature(context, feature):
    config = getattr(setup_before_all, 'config', None)
    if config is not None:
        app_factory = setup_before_all.app_factory
    else:
        # superdesk-aap don't use "setup_before_all" already
        config = getattr(setup_before_scenario, 'config', None)
        app_factory = getattr(setup_before_scenario, 'app_factory', None)
    config = config or {}
    app_factory = app_factory or get_app

    # set the MAX_TRANSMIT_RETRY_ATTEMPT to zero so that transmit does not retry
    config['MAX_TRANSMIT_RETRY_ATTEMPT'] = 0
    os.environ['BEHAVE_TESTING'] = '1'
    tests.setup(context, config, app_factory=app_factory)

    if 'tobefixed' in feature.tags:
        feature.mark_skipped()

    if 'dbauth' in feature.tags and LDAP_SERVER:
        feature.mark_skipped()

    if 'ldapauth' in feature.tags and not LDAP_SERVER:
        feature.mark_skipped()


def before_scenario(context, scenario):
    config = {}
    setup_before_scenario(context, scenario, config, app_factory=get_app)


def after_scenario(context, scenario):
    if 'provider' in scenario.tags:
        teardown_providers(context)

    if 'notification' in scenario.tags:
        tests.teardown_notification(context)

    if 'clean' in scenario.tags:
        try:
            os.remove(get_macro_path('behave_macro.py'))
            os.remove(get_macro_path('validate_headline_macro.py'))
        except:
            pass


def before_step(context, step):
    if LDAP_SERVER and step.text:
        try:
            step_text_json = json.loads(step.text)
            step_text_json = {k: step_text_json[k] for k in step_text_json.keys() if k not in readonly_fields} \
                if isinstance(step_text_json, dict) else \
                [{k: json_obj[k] for k in json_obj.keys() if k not in readonly_fields} for json_obj in step_text_json]

            step.text = json.dumps(step_text_json)
        except:
            pass


def setup_search_provider(app):
    from apps.search_providers import register_search_provider, allowed_search_providers
    if 'testsearch' not in allowed_search_providers:
        register_search_provider('testsearch', provider_class=TestSearchProvider)

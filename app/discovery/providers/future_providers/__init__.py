"""Drop-in directory for future/third-party discovery providers.

Place a module here exposing `build(config) -> DiscoveryProvider` or a
`PROVIDER` class; load it via
`app.discovery.providers.custom_provider.load_plugin_provider`.
"""

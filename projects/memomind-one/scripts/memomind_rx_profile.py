"""Closed offline RX allocation profiles; never derive authority from a manifest.

Callers explicitly select a literal profile. The default remains the historical
64 KiB policy. Neither a caller-supplied byte limit nor a manifest can widen it.
"""
DEFAULT_RX_PROFILE = 'app-rx-64k-v1'
EXTENDED_RX_PROFILE = 'app-rx-96k-v1'
RX_PROFILES = (DEFAULT_RX_PROFILE, EXTENDED_RX_PROFILE)


def rx_limit(profile=DEFAULT_RX_PROFILE):
    if type(profile) is not str or profile not in RX_PROFILES:
        raise ValueError('Unknown fixed RX profile')
    return 65536 if profile == DEFAULT_RX_PROFILE else 98304


def linker_name(profile=DEFAULT_RX_PROFILE):
    rx_limit(profile)
    return 'graphics.ld' if profile == DEFAULT_RX_PROFILE else 'graphics_rx96.ld'


def mark_manifest(manifest, profile=DEFAULT_RX_PROFILE):
    """Leave historical manifests exact; distinct 96 KiB formats are offline only."""
    limit = rx_limit(profile)
    if profile != DEFAULT_RX_PROFILE:
        manifest.update(format=manifest['format']+'-rx96', rx_profile=profile,
                        rx_limit_bytes=limit, live_flashing_enabled=False)


def add_rx_argument(parser):
    parser.add_argument('--rx-profile', choices=RX_PROFILES, default=DEFAULT_RX_PROFILE,
                        help='Explicit fixed RX allocation; 96 KiB construction is offline only')

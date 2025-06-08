DEFAULTS = {
    "label": "0",
    "label_alt": "0",
    "update_interval": 3600,
    "city": "Jakarta",
    "country": "ID",
    "method": 8,
    "callbacks": {
        "on_left": "do_nothing",
        "on_middle": "do_nothing",
        "on_right": "do_nothing",
    },
    'container_padding': {'top': 0, 'left': 0, 'bottom': 0, 'right': 0},
    'animation': {
        'enabled': True,
        'type': 'fadeInOut',
        'duration': 200
    },
    'prayer_card': {
        'blur': True,
        'round_corners': True,
        'round_corners_type': 'normal',
        'border_color': 'System',
        'alignment': 'right',
        'direction': 'down',
        'distance': 6, # deprecated
        'offset_top': 6,
        'offset_left': 0,
        'icon_size': 64
    },
}

VALIDATION_SCHEMA = {
    "label": {"type": "string", "default": DEFAULTS["label"]},
    "label_alt": {"type": "string", "default": DEFAULTS["label_alt"]},
    "update_interval": {
        "type": "integer",
        "default": DEFAULTS["update_interval"],
        "min": 60,
        "max": 36000000,
    },
    "city": {"type": "string", "default": DEFAULTS["city"]},
    "country": {"type": "string", "default": DEFAULTS["country"]},
    "method": {"type": "integer", "default": DEFAULTS["method"], "min": 0, "max": 99},
    "tune": {
        "type": "dict",
        "schema": {
            "Imsak": {"type": "integer", "default": 0},
            "Fajr": {"type": "integer", "default": 0},
            "Sunrise": {"type": "integer", "default": 0},
            "Dhuhr": {"type": "integer", "default": 0},
            "Asr": {"type": "integer", "default": 0},
            "Maghrib": {"type": "integer", "default": 0},
            "Sunset": {"type": "integer", "default": 0},
            "Isha": {"type": "integer", "default": 0},
            "Midnight": {"type": "integer", "default": 0},
        },
        "default": {},
    },
    'prayer_card': {
        'type': 'dict',
        'schema': {
            'blur': {
                'type': 'boolean',
                'default': DEFAULTS['prayer_card']['blur']
            },
            'round_corners': {
                'type': 'boolean',
                'default': DEFAULTS['prayer_card']['round_corners']
            },
            'round_corners_type': {
                'type': 'string',
                'default': DEFAULTS['prayer_card']['round_corners_type'],
                'allowed': ['normal', 'small']
            },
            'border_color': {
                'type': 'string',
                'default': DEFAULTS['prayer_card']['border_color']
            },
            'alignment': {
                'type': 'string',
                'default': DEFAULTS['prayer_card']['alignment']
            },
            'direction': {
                'type': 'string',
                'default': DEFAULTS['prayer_card']['direction']
            },
            'distance': {
                'type': 'integer',
                'default': DEFAULTS['prayer_card']['distance']
            },
            'offset_top': {
                'type': 'integer',
                'default': DEFAULTS['prayer_card']['offset_top']
            },
            'offset_left': {
                'type': 'integer',
                'default': DEFAULTS['prayer_card']['offset_left']
            },
            'icon_size': {
                'type': 'integer',
                'default': DEFAULTS['prayer_card']['icon_size']
            }
        },
        'default': DEFAULTS['prayer_card']
    },
    'animation': {
        'type': 'dict',
        'schema': {
            'enabled': {
                'type': 'boolean',
                'default': DEFAULTS['animation']['enabled']
            },
            'type': {
                'type': 'string',
                'default': DEFAULTS['animation']['type']
            },
            'duration': {
                'type': 'integer',
                'default': DEFAULTS['animation']['duration']
            }
        },
        'default': DEFAULTS['animation']
    },
    'container_padding': {
        'type': 'dict',
        'required': False,
        'schema': {
            'top': {
                'type': 'integer',
                'default': DEFAULTS['container_padding']['top']
            },
            'left': {
                'type': 'integer',
                'default': DEFAULTS['container_padding']['left']
            },
            'bottom': {
                'type': 'integer',
                'default': DEFAULTS['container_padding']['bottom']
            },
            'right': {
                'type': 'integer',
                'default': DEFAULTS['container_padding']['right']
            }
        },
        'default': DEFAULTS['container_padding']
    },
    "callbacks": {
        "type": "dict",
        "schema": {
            "on_left": {
                "type": "string",
                "nullable": True,
                "default": DEFAULTS["callbacks"]["on_left"],
            },
            "on_middle": {
                "type": "string",
                "nullable": True,
                "default": DEFAULTS["callbacks"]["on_middle"],
            },
            "on_right": {
                "type": "string",
                "nullable": True,
                "default": DEFAULTS["callbacks"]["on_right"],
            },
        },
        "default": DEFAULTS["callbacks"],
    },
}

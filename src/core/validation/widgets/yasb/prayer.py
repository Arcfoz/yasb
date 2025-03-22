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

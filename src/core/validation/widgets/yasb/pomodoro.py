DEFAULTS = {
    'label': '\uf252 {remaining}',
    'label_alt': '{session}/{total_sessions} - {remaining}',
    'work_duration': 25,
    'break_duration': 5,
    'long_break_duration': 15,
    'long_break_interval': 4,
    'auto_start_breaks': True,
    'auto_start_work': True,
    'sound_notification': True,
    'show_notification': True,
    'session_target': 0,
    'hide_on_break': False,
    'animation': {
        'enabled': True,
        'type': 'fadeInOut',
        'duration': 200
    },
    'container_padding': {'top': 0, 'left': 0, 'bottom': 0, 'right': 0},
    'callbacks': {
        'on_left': 'toggle_timer',
        'on_middle': 'reset_timer',
        'on_right': 'toggle_label'
    },
    'icons': {
        'work': '\uf252',
        'break': '\uf253',
        'paused': '\uf254',
    },
    'menu': {
        'blur': True,
        'round_corners': True,
        'round_corners_type': 'normal',
        'border_color': 'System',
        'alignment': 'right',
        'direction': 'down',
        'offset_top': 6,
        'offset_left': 0,
        'circle_background_color': '#09ffffff',
        'circle_work_progress_color': '#a6e3a1',
        'circle_break_progress_color': '#89b4fa',
        'circle_thickness': 8,
        'circle_size': 160,
    }
}

VALIDATION_SCHEMA = {
    'label': {
        'type': 'string',
        'default': DEFAULTS['label']
    },
    'label_alt': {
        'type': 'string',
        'default': DEFAULTS['label_alt']
    },
    'work_duration': {
        'type': 'integer',
        'min': 1,
        'default': DEFAULTS['work_duration']
    },
    'break_duration': {
        'type': 'integer',
        'min': 1,
        'default': DEFAULTS['break_duration']
    },
    'long_break_duration': {
        'type': 'integer',
        'min': 1,
        'default': DEFAULTS['long_break_duration']
    },
    'long_break_interval': {
        'type': 'integer',
        'min': 1,
        'default': DEFAULTS['long_break_interval']
    },
    'auto_start_breaks': {
        'type': 'boolean',
        'default': DEFAULTS['auto_start_breaks']
    },
    'auto_start_work': {
        'type': 'boolean',
        'default': DEFAULTS['auto_start_work']
    },
    'sound_notification': {
        'type': 'boolean',
        'default': DEFAULTS['sound_notification']
    },
    'show_notification': {
        'type': 'boolean',
        'default': DEFAULTS['show_notification']
    },
    'session_target': {
        'type': 'integer',
        'min': 0,
        'default': DEFAULTS['session_target']
    },
    'hide_on_break': {
        'type': 'boolean',
        'default': DEFAULTS['hide_on_break']
    },
    'icons': {
        'type': 'dict',
        'required': False,
        'schema': {
            'work': {
                'type': 'string',
                'default': DEFAULTS['icons']['work']
            },
            'break': {
                'type': 'string',
                'default': DEFAULTS['icons']['break']
            },
            'paused': {
                'type': 'string',
                'default': DEFAULTS['icons']['paused']
            }
        },
        'default': DEFAULTS['icons']
    },
    'animation': {
        'type': 'dict',
        'required': False,
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
    'callbacks': {
        'type': 'dict',
        'schema': {
            'on_left': {
                'type': 'string',
                'default': DEFAULTS['callbacks']['on_left'],
            },
            'on_middle': {
                'type': 'string',
                'default': DEFAULTS['callbacks']['on_middle'],
            },
            'on_right': {
                'type': 'string',
                'default': DEFAULTS['callbacks']['on_right']
            }
        },
        'default': DEFAULTS['callbacks']
    },
    'menu': {
        'type': 'dict',
        'required': False,
        'schema': {
            'blur': {
                'type': 'boolean',
                'default': DEFAULTS['menu']['blur']
            },
            'round_corners': {
                'type': 'boolean',
                'default': DEFAULTS['menu']['round_corners']
            },
            'round_corners_type': {
                'type': 'string',
                'default': DEFAULTS['menu']['round_corners_type'],
                'allowed': ['normal', 'small']
            },
            'border_color': {
                'type': 'string',
                'default': DEFAULTS['menu']['border_color']
            },
            'alignment': {
                'type': 'string',
                'default': DEFAULTS['menu']['alignment']
            },
            'direction': {
                'type': 'string',
                'default': DEFAULTS['menu']['direction']
            },
            'offset_top': {
                'type': 'integer',
                'default': DEFAULTS['menu']['offset_top']
            },
            'offset_left': {
                'type': 'integer',
                'default': DEFAULTS['menu']['offset_left']
            },
            'circle_background_color': {
                'type': 'string',
                'default': DEFAULTS['menu']['circle_background_color']
            },
            'circle_work_progress_color': {
                'type': 'string',
                'default': DEFAULTS['menu']['circle_work_progress_color']
            },
            'circle_break_progress_color': {
                'type': 'string',
                'default': DEFAULTS['menu']['circle_break_progress_color']
            },
            'circle_thickness': {
                'type': 'integer',
                'default': DEFAULTS['menu']['circle_thickness']
            },
            'circle_size': {
                'type': 'integer',
                'default': DEFAULTS['menu']['circle_size']
            }
        },
        'default': DEFAULTS['menu']
    }
}
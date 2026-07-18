import { importShared } from './__federation_fn_import.js';

const { defineComponent: _defineComponent } = await importShared('vue');

const { resolveComponent: _resolveComponent, createVNode: _createVNode, createElementVNode: _createElementVNode, withCtx: _withCtx, createTextVNode: _createTextVNode, openBlock: _openBlock, createElementBlock: _createElementBlock, createCommentVNode: _createCommentVNode, Fragment: _Fragment } = await importShared('vue');

const { reactive, watch, ref } = await importShared('vue');

var msgTypeOptions = [
  { title: '下载', value: 'Download' },
  { title: '整理', value: 'Organize' },
  { title: '订阅', value: 'Subscribe' },
  { title: '站点', value: 'SiteMessage' },
  { title: '系统', value: 'System' },
  { title: '用户', value: 'User' },
  { title: '媒体服务器', value: 'MediaServer' },
  { title: '插件', value: 'Plugin' }
];

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { type: Object, default: function() { return {}; } },
    api: { type: Object, default: function() { return {}; } },
    pluginId: String
  },
  emits: ["save", "close", "switch"],
  setup(props, { emit }) {
    var config = reactive({
      enabled: false,
      onlyonce: false,
      clear_history: false,
      uid: '',
      sendkey: '',
      msgtypes: [],
      history_limit: 50,
      show_sidebar: true
    });

    function mergeConfig(src) {
      if (!src) return;
      config.enabled = src.enabled || false;
      config.onlyonce = src.onlyonce || false;
      config.clear_history = src.clear_history || false;
      config.uid = src.uid || '';
      config.sendkey = src.sendkey || '';
      config.msgtypes = src.msgtypes || [];
      config.history_limit = src.history_limit || 50;
      config.show_sidebar = src.show_sidebar !== undefined ? src.show_sidebar : true;
    }

    mergeConfig(props.initialConfig);

    watch(function() { return props.initialConfig; }, function(val) {
      mergeConfig(val);
    }, { deep: true });

    var saving = ref(false);
    var snackbar = reactive({ show: false, text: '', color: 'success' });

    async function handleSave() {
      saving.value = true;
      try {
        var pluginId = props.pluginId || 'ServerChan3Msg';
        emit('save', Object.assign({}, config));
        await props.api.post('plugin/' + pluginId + '/config', Object.assign({}, config)).catch(function() {});
        snackbar.text = '配置已保存';
        snackbar.color = 'success';
        snackbar.show = true;
      } catch (e) {
        snackbar.text = '保存失败';
        snackbar.color = 'error';
        snackbar.show = true;
      } finally {
        saving.value = false;
      }
    }

    function toggleMsgType(val) {
      var arr = config.msgtypes.slice();
      var pos = arr.indexOf(val);
      if (pos === -1) {
        arr.push(val);
      } else {
        arr.splice(pos, 1);
      }
      config.msgtypes = arr;
    }

    return function(_ctx, _cache) {
      var _component_v_icon = _resolveComponent("v-icon");
      var _component_v_btn = _resolveComponent("v-btn");
      var _component_v_btn_group = _resolveComponent("v-btn-group");
      var _component_v_row = _resolveComponent("v-row");
      var _component_v_col = _resolveComponent("v-col");
      var _component_v_text_field = _resolveComponent("v-text-field");
      var _component_v_checkbox = _resolveComponent("v-checkbox");
      var _component_v_snackbar = _resolveComponent("v-snackbar");

      function buildCheckboxes(cfg, options) {
        var boxes = [];
        for (var i = 0; i < options.length; i++) {
          var opt = options[i];
          (function(val, title) {
            boxes.push(_createVNode(_component_v_checkbox, {
              label: title,
              density: "compact",
              "hide-details": true,
              modelValue: cfg.msgtypes.indexOf(val) !== -1,
              "onUpdate:modelValue": function(checked) {
                if (checked) {
                  if (cfg.msgtypes.indexOf(val) === -1) {
                    cfg.msgtypes = cfg.msgtypes.concat([val]);
                  }
                } else {
                  var idx = cfg.msgtypes.indexOf(val);
                  if (idx !== -1) {
                    var arr = cfg.msgtypes.slice();
                    arr.splice(idx, 1);
                    cfg.msgtypes = arr;
                  }
                }
              }
            }));
          })(opt.value, opt.title);
        }
        return boxes;
      }

      var children = [];

      // Topbar
      children.push(_createElementVNode("div", { class: "sc3-topbar" }, [
        _createElementVNode("div", { class: "sc3-topbar__left" }, [
          _createElementVNode("div", { class: "sc3-topbar__icon" }, [
            _createVNode(_component_v_icon, { icon: "mdi-cog", size: "24" })
          ]),
          _createElementVNode("div", null, [
            _createElementVNode("div", { class: "sc3-topbar__title" }, "Server酱³ · 配置"),
            _createElementVNode("div", { class: "sc3-topbar__sub" }, "ServerChan3 Plugin")
          ])
        ]),
        _createElementVNode("div", { class: "sc3-topbar__right", style: { padding: "2px" } }, [
          _createVNode(_component_v_btn_group, { variant: "tonal", density: "compact", class: "elevation-0" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_btn, { color: "primary", onClick: function($event) { emit("switch", "page"); }, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
                default: _withCtx(function() { return [
                  _createVNode(_component_v_icon, { icon: "mdi-view-dashboard", size: "18", class: "mr-sm-1" }),
                  _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "状态页")
                ]; })
              }),
              _createVNode(_component_v_btn, { color: "primary", onClick: handleSave, loading: saving.value, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
                default: _withCtx(function() { return [
                  _createVNode(_component_v_icon, { icon: "mdi-content-save", size: "18", class: "mr-sm-1" }),
                  _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "保存")
                ]; })
              }, 8, ["loading"]),
              _createVNode(_component_v_btn, { color: "primary", onClick: function($event) { emit("close"); }, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
                default: _withCtx(function() { return [
                  _createVNode(_component_v_icon, { icon: "mdi-close", size: "18" })
                ]; })
              })
            ]; })
          })
        ])
      ]));

      // ===== Card: 基础设置 =====
      var cardChildren = [];

      // Card header
      cardChildren.push(_createElementVNode("div", { class: "sc3-card__header" }, [
        _createElementVNode("span", { class: "sc3-card__title" }, [
          _createVNode(_component_v_icon, { icon: "mdi-tune-vertical", size: "18", class: "mr-1" }),
          _createTextVNode(" 基础设置")
        ])
      ]));

      // Row: 启用插件 + 显示侧栏
      cardChildren.push(_createVNode(_component_v_row, { class: "mt-1 mb-1" }, {
        default: _withCtx(function() { return [
          _createVNode(_component_v_col, { cols: "12", sm: "6", class: "d-flex align-center justify-space-between py-1" }, {
            default: _withCtx(function() { return [
              _createElementVNode("span", { class: "sc3-row__text" }, [
                _createVNode(_component_v_icon, { icon: "mdi-power-plug", size: "20", color: config.enabled ? "#667eea" : "grey", class: "mr-2" }, null, 8, ["color"]),
                _createTextVNode(" 启用插件")
              ]),
              _createElementVNode("label", { class: "sc3-switch", style: { "--switch-checked-bg": "#667eea" } }, [
                _createElementVNode("input", { type: "checkbox", checked: config.enabled ? true : null, onChange: function($event) { config.enabled = $event.target.checked; } }),
                _createElementVNode("div", { class: "sc3-slider" }, [
                  _createElementVNode("div", { class: "sc3-circle" }, [
                    _createElementVNode("svg", { class: "sc3-cross", viewBox: "0 0 365.696 365.696", height: "6", width: "6" }, [
                      _createElementVNode("g", null, [
                        _createElementVNode("path", { d: "M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0", fill: "currentColor" })
                      ])
                    ]),
                    _createElementVNode("svg", { class: "sc3-checkmark", viewBox: "0 0 24 24", height: "10", width: "10" }, [
                      _createElementVNode("g", null, [
                        _createElementVNode("path", { d: "M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z", fill: "currentColor" })
                      ])
                    ])
                  ])
                ])
              ])
            ]; })
          }),
          _createVNode(_component_v_col, { cols: "12", sm: "6", class: "d-flex align-center justify-space-between py-1" }, {
            default: _withCtx(function() { return [
              _createElementVNode("span", { class: "sc3-row__text" }, [
                _createVNode(_component_v_icon, { icon: "mdi-menu", size: "20", color: config.show_sidebar ? "#667eea" : "grey", class: "mr-2" }, null, 8, ["color"]),
                _createTextVNode(" 显示侧栏")
              ]),
              _createElementVNode("label", { class: "sc3-switch", style: { "--switch-checked-bg": "#667eea" } }, [
                _createElementVNode("input", { type: "checkbox", checked: config.show_sidebar ? true : null, onChange: function($event) { config.show_sidebar = $event.target.checked; } }),
                _createElementVNode("div", { class: "sc3-slider" }, [
                  _createElementVNode("div", { class: "sc3-circle" }, [
                    _createElementVNode("svg", { class: "sc3-cross", viewBox: "0 0 365.696 365.696", height: "6", width: "6" }, [
                      _createElementVNode("g", null, [
                        _createElementVNode("path", { d: "M243.188 182.86 356.32 69.726c12.5-12.5 12.5-32.766 0-45.247L341.238 9.398c-12.504-12.503-32.77-12.503-45.25 0L182.86 122.528 69.727 9.374c-12.5-12.5-32.766-12.5-45.247 0L9.375 24.457c-12.5 12.504-12.5 32.77 0 45.25l113.152 113.152L9.398 295.99c-12.503 12.503-12.503 32.769 0 45.25L24.48 356.32c12.5 12.5 32.766 12.5 45.247 0l113.132-113.132L295.99 356.32c12.503 12.5 32.769 12.5 45.25 0l15.081-15.082c12.5-12.504 12.5-32.77 0-45.25zm0 0", fill: "currentColor" })
                      ])
                    ]),
                    _createElementVNode("svg", { class: "sc3-checkmark", viewBox: "0 0 24 24", height: "10", width: "10" }, [
                      _createElementVNode("g", null, [
                        _createElementVNode("path", { d: "M9.707 19.121a.997.997 0 0 1-1.414 0l-5.646-5.647a1.5 1.5 0 0 1 0-2.121l.707-.707a1.5 1.5 0 0 1 2.121 0L9 14.171l9.525-9.525a1.5 1.5 0 0 1 2.121 0l.707.707a1.5 1.5 0 0 1 0 2.121z", fill: "currentColor" })
                      ])
                    ])
                  ])
                ])
              ])
            ]; })
          })
        ]; })
      }));

      // Divider
      cardChildren.push(_createElementVNode("div", { class: "sc3-divider" }));

      // Field: SendKey + UID + 历史保留条数 in one row (three columns)
      cardChildren.push(_createElementVNode("div", { class: "sc3-field" }, [
        _createVNode(_component_v_row, { dense: "" }, {
          default: _withCtx(function() { return [
            _createVNode(_component_v_col, { cols: "12", md: "4" }, {
              default: _withCtx(function() { return [
                _createElementVNode("label", { class: "sc3-field__label mb-1" }, [
                  _createVNode(_component_v_icon, { icon: "mdi-key-variant", size: "18", color: "warning", class: "mr-1" }),
                  _createTextVNode(" SendKey")
                ]),
                _createVNode(_component_v_text_field, {
                  modelValue: config.sendkey,
                  "onUpdate:modelValue": function($event) { config.sendkey = $event; },
                  label: "SendKey",
                  placeholder: "sctp123456txxxxxxxxxxxx",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "auto",
                  color: "primary",
                  class: "sc3-input"
                })
              ]; })
            }),
            _createVNode(_component_v_col, { cols: "12", md: "4" }, {
              default: _withCtx(function() { return [
                _createElementVNode("label", { class: "sc3-field__label mb-1" }, [
                  _createVNode(_component_v_icon, { icon: "mdi-account-key", size: "18", color: "info", class: "mr-1" }),
                  _createTextVNode(" UID")
                ]),
                _createVNode(_component_v_text_field, {
                  modelValue: config.uid,
                  "onUpdate:modelValue": function($event) { config.uid = $event; },
                  label: "UID",
                  placeholder: "从 SendKey 页面获取，如 354",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "auto",
                  color: "primary",
                  class: "sc3-input"
                })
              ]; })
            }),
            _createVNode(_component_v_col, { cols: "12", md: "4" }, {
              default: _withCtx(function() { return [
                _createElementVNode("label", { class: "sc3-field__label mb-1" }, [
                  _createVNode(_component_v_icon, { icon: "mdi-history", size: "18", color: "primary", class: "mr-1" }),
                  _createTextVNode(" 历史保留条数")
                ]),
                _createVNode(_component_v_text_field, {
                  modelValue: config.history_limit,
                  "onUpdate:modelValue": function($event) { config.history_limit = $event; },
                  label: "历史保留条数",
                  placeholder: "50",
                  type: "number",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "auto",
                  color: "primary",
                  hint: "最多保留的历史发送记录条数",
                  "persistent-hint": "",
                  min: 10,
                  max: 500,
                  class: "sc3-input"
                })
              ]; })
            })
          ]; })
        })
      ]));

      children.push(_createElementVNode("div", { class: "sc3-card" }, cardChildren));

      // Snackbar
      children.push(_createVNode(_component_v_snackbar, {
        modelValue: snackbar.show,
        "onUpdate:modelValue": function($event) { snackbar.show = $event; },
        color: snackbar.color,
        timeout: "2500",
        location: "top"
      }, {
        default: _withCtx(function() { return [
          _createTextVNode(_toDisplayString(snackbar.text))
        ]; })
      }, 8, ["modelValue", "color"]));

      return _createElementVNode("div", { class: "sc3-config" }, children);
    };
  }
});

export default _sfc_main;

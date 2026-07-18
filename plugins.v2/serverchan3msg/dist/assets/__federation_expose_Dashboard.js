import { importShared } from './__federation_fn_import.js';

const { defineComponent: _defineComponent } = await importShared('vue');

const { resolveComponent: _resolveComponent, createVNode: _createVNode, createElementVNode: _createElementVNode, withCtx: _withCtx, createTextVNode: _createTextVNode, openBlock: _openBlock, createElementBlock: _createElementBlock, createCommentVNode: _createCommentVNode, Fragment: _Fragment, toDisplayString: _toDisplayString } = await importShared('vue');

const { ref, onMounted } = await importShared('vue');

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Dashboard",
  props: {
    api: { type: [Object, Function], required: true },
    config: { type: Object, default: function() { return {}; } },
    allowRefresh: { type: Boolean, default: false },
    refreshInterval: { type: Number, default: 0 }
  },
  setup(props) {
    var stats = ref({ enabled: false, has_sendkey: false, msgtype_count: 0, history_count: 0 });
    var history = ref([]);
    var loading = ref(true);
    var clearing = ref(false);

    async function fetchData() {
      loading.value = true;
      try {
        var s = await props.api.get('plugin/ServerChan3Msg/stats');
        if (s) stats.value = s;
      } catch (e) {
        console.warn('[SC3] Stats error:', e);
      }
      try {
        var h = await props.api.get('plugin/ServerChan3Msg/history?page=1&page_size=20');
        if (h && h.items) history.value = h.items;
      } catch (e) {
        console.warn('[SC3] History error:', e);
      }
      loading.value = false;
    }

    async function deleteRecord(time) {
      try {
        var res = await props.api.post('plugin/ServerChan3Msg/history/delete', { time: time });
        if (res && res.success) {
          await fetchData();
        }
      } catch (e) {
        console.warn('[SC3] Delete error:', e);
      }
    }

    async function clearHistory() {
      clearing.value = true;
      try {
        var res = await props.api.post('plugin/ServerChan3Msg/history/clear', {});
        if (res && res.success) {
          await fetchData();
        }
      } catch (e) {
        console.warn('[SC3] Clear error:', e);
      }
      clearing.value = false;
    }

    onMounted(function() { fetchData(); });

    return function(_ctx, _cache) {
      var _component_v_icon = _resolveComponent("v-icon");
      var _component_v_chip = _resolveComponent("v-chip");
      var _component_v_card = _resolveComponent("v-card");
      var _component_v_card_item = _resolveComponent("v-card-item");
      var _component_v_card_title = _resolveComponent("v-card-title");
      var _component_v_card_subtitle = _resolveComponent("v-card-subtitle");
      var _component_v_card_text = _resolveComponent("v-card-text");
      var _component_v_progress_circular = _resolveComponent("v-progress-circular");
      var _component_v_btn = _resolveComponent("v-btn");

      var cfg = props.config || {};
      var title = (cfg.title || (cfg.attrs && cfg.attrs.title) || '发送概览');
      var subtitle = (cfg.subtitle || (cfg.attrs && cfg.attrs.subtitle) || '');

      if (loading.value) {
        return _createElementVNode("div", { class: "d-flex flex-column h-100 w-100" }, [
          _createVNode(_component_v_card, { class: "fill-height d-flex align-center justify-center" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_progress_circular, { indeterminate: "", color: "primary", size: "32" })
            ]; })
          })
        ]);
      }

      // Overview + History combined
      var s = stats.value;
      var items = history.value;
      var rows = [];

      // Overview row
      var overviewChildren = [];
      overviewChildren.push(_createElementVNode("div", { class: "d-flex text-center px-2 pt-2 pb-1" }, [
        _createElementVNode("div", { class: "flex-1 d-flex flex-column align-center" }, [
          _createVNode(_component_v_icon, { icon: "mdi-power-plug", size: "14", color: "primary" }),
          _createElementVNode("div", { class: "text-body-2 font-weight-bold mt-1" }, _toDisplayString(s.enabled ? '已启用' : '未启用')),
          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "运行状态")
        ]),
        _createElementVNode("div", { class: "flex-1 d-flex flex-column align-center" }, [
          _createVNode(_component_v_icon, { icon: "mdi-key-variant", size: "14", color: "#764ba2" }),
          _createElementVNode("div", { class: "text-body-2 font-weight-bold mt-1", style: "color:#764ba2" }, _toDisplayString(s.has_sendkey ? '已配置' : '未配置')),
          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "SendKey")
        ]),
        _createElementVNode("div", { class: "flex-1 d-flex flex-column align-center" }, [
          _createVNode(_component_v_icon, { icon: "mdi-message-text-outline", size: "14", color: "#f093fb" }),
          _createElementVNode("div", { class: "text-body-2 font-weight-bold mt-1", style: "color:#f093fb" }, _toDisplayString(s.msgtype_count || '全部')),
          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "消息类型")
        ]),
        _createElementVNode("div", { class: "flex-1 d-flex flex-column align-center" }, [
          _createVNode(_component_v_icon, { icon: "mdi-history", size: "14", color: "#4facfe" }),
          _createElementVNode("div", { class: "text-body-2 font-weight-bold mt-1", style: "color:#4facfe" }, _toDisplayString(s.history_count)),
          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "发送记录")
        ])
      ]));

      // History list
      if (items.length === 0) {
        rows.push(_createElementVNode("div", { class: "text-center py-6 text-medium-emphasis" }, "暂无发送记录"));
      } else {
        for (var i = 0; i < items.length; i++) {
          var row = items[i];
          var chipColor = row.success ? 'success' : 'error';
          var chipText = row.success ? '成功' : '失败';
          var textPreview = row.text ? row.text.substring(0, 80) + (row.text.length > 80 ? '...' : '') : '';
          rows.push(_createElementVNode("div", { class: "d-flex align-center pa-3" + (i < items.length - 1 ? " border-b" : "") }, [
            _createElementVNode("div", { class: "flex-grow-1 min-w-0" }, [
              _createElementVNode("div", { class: "d-flex align-center gap-2 text-body-2 font-weight-medium min-w-0 text-high-emphasis" }, [
                _createElementVNode("span", { class: "text-truncate" }, _toDisplayString(row.title || '(无标题)'))
              ]),
              _createElementVNode("div", { class: "d-flex align-center gap-1 mt-1" }, [
                _createElementVNode("span", { class: "text-caption text-disabled" }, _toDisplayString(row.time)),
                row.msg_type ? _createElementVNode("span", { class: "text-caption text-disabled ml-1" }, _toDisplayString('/ ' + row.msg_type)) : null
              ]),
              textPreview ? _createElementVNode("div", { class: "text-caption text-medium-emphasis mt-1 text-truncate" }, _toDisplayString(textPreview)) : null,
              row.error ? _createElementVNode("div", { class: "text-caption text-error mt-1" }, _toDisplayString(row.error)) : null
            ]),
            _createVNode(_component_v_btn, {
              icon: "mdi-delete",
              size: "x-small",
              variant: "text",
              color: "grey",
              class: "flex-shrink-0 mr-1",
              onClick: function(t) { return function() { deleteRecord(t); }; }(row.time)
            }),
            _createVNode(_component_v_chip, { color: chipColor, size: "x-small", class: "flex-shrink-0" }, {
              default: _withCtx(function() { return [_createTextVNode(_toDisplayString(chipText))]; })
            })
          ]));
        }
      }

      return _createElementVNode("div", { class: "d-flex flex-column h-100 w-100" }, [
        _createVNode(_component_v_card, { class: "fill-height d-flex flex-column" }, {
          default: _withCtx(function() { return [
            _createVNode(_component_v_card_item, { class: "pb-2" }, {
              append: _withCtx(function() { return [
                _createVNode(_component_v_btn, {
                  size: "small",
                  variant: "text",
                  color: "primary",
                  class: "flex-shrink-0",
                  onClick: function() { window.location.hash = '/plugins?tab=detail&id=ServerChan3Msg'; }
                }, {
                  default: _withCtx(function() { return [_createTextVNode("查看全部")]; })
                }),
                items.length > 0 ? _createVNode(_component_v_btn, {
                  size: "small",
                  variant: "text",
                  color: "error",
                  class: "flex-shrink-0",
                  icon: "mdi-delete-sweep",
                  loading: clearing.value,
                  onClick: clearHistory
                }) : null
              ]; }),
              default: _withCtx(function() { return [
                _createVNode(_component_v_card_title, { class: "d-flex flex-wrap align-center gap-2 ps-0" }, {
                  default: _withCtx(function() { return [
                    _createVNode(_component_v_icon, { icon: "mdi-chart-box-outline", color: "primary", size: "small" }),
                    _createElementVNode("span", null, _toDisplayString(title))
                  ]; })
                }),
                subtitle ? _createVNode(_component_v_card_subtitle, null, {
                  default: _withCtx(function() { return [_createTextVNode(_toDisplayString(subtitle))]; })
                }) : null
              ]; })
            }),
            _createVNode(_component_v_card_text, { class: "flex-grow-1 pa-3 pt-0 d-flex flex-column" }, {
              default: _withCtx(function() { return [
                overviewChildren,
                _createElementVNode("div", { class: "flex-grow-1", style: "overflow-y:auto;min-height:0" }, rows)
              ]; })
            })
          ]; })
        })
      ]);
    };
  }
});

export default _sfc_main;

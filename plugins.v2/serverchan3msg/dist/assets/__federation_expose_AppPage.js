import { importShared } from './__federation_fn_import.js';

const { defineComponent: _defineComponent } = await importShared('vue');

const { resolveComponent: _resolveComponent, createVNode: _createVNode, createElementVNode: _createElementVNode, withCtx: _withCtx, createTextVNode: _createTextVNode, openBlock: _openBlock, createElementBlock: _createElementBlock, createCommentVNode: _createCommentVNode, Fragment: _Fragment, toDisplayString: _toDisplayString } = await importShared('vue');

const { ref, reactive, computed, onMounted } = await importShared('vue');

const pageSize = 10;

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "AppPage",
  props: {
    api: { type: Object, default: function() { return {}; } },
    pluginId: String,
    navKey: String
  },
  setup(props) {
    var pluginId = props.pluginId || 'ServerChan3Msg';
    var stats = reactive({ enabled: false, has_sendkey: false, msgtype_count: 0, history_count: 0, last_run: null });
    var latest = ref(null);
    var selectedRecord = ref(null);
    var history = ref([]);
    var historyTotal = ref(0);
    var page = ref(1);
    var sending = ref(false);
    var clearing = ref(false);
    var snackbar = reactive({ show: false, text: '', color: 'success' });

    var pagedHistory = computed(function() {
      var start = (page.value - 1) * pageSize;
      return history.value.slice(start, start + pageSize);
    });

    var totalPages = computed(function() {
      return Math.ceil(history.value.length / pageSize);
    });

    async function fetchData() {
      try {
        var s = await props.api.get('plugin/' + pluginId + '/stats');
        if (s) {
          stats.enabled = s.enabled || false;
          stats.has_sendkey = s.has_sendkey || false;
          stats.msgtype_count = s.msgtype_count || 0;
          stats.history_count = s.history_count || 0;
        }
        var l = await props.api.get('plugin/' + pluginId + '/latest');
        if (l && l.has_data) {
          latest.value = l.record;
          if (!selectedRecord.value) selectedRecord.value = l.record;
        }
        var h = await props.api.get('plugin/' + pluginId + '/history?page=1&page_size=999');
        if (h && h.items) {
          history.value = h.items;
          historyTotal.value = h.total;
          if (h.items.length > 0) stats.last_run = h.items[0].time;
        }
      } catch (e) {
        console.warn('[SC3] Fetch error:', e);
      }
    }

    async function testSend() {
      sending.value = true;
      try {
        var res = await props.api.get('plugin/' + pluginId + '/test');
        showSnack(res && res.message || (res && res.success ? '发送成功' : '发送失败'), res && res.success ? 'success' : 'error');
        await fetchData();
      } catch (e) {
        showSnack('请求失败', 'error');
      }
      sending.value = false;
    }

    async function deleteRecord(time) {
      try {
        var res = await props.api.post('plugin/' + pluginId + '/history/delete', { time: time });
        if (res && res.success) {
          showSnack('已删除', 'success');
          await fetchData();
          if (selectedRecord.value && selectedRecord.value.time === time) {
            selectedRecord.value = history.value.length > 0 ? history.value[0] : null;
          }
        } else {
          showSnack(res && res.message || '删除失败', 'error');
        }
      } catch (e) {
        showSnack('删除请求失败', 'error');
      }
    }

    async function clearHistory() {
      clearing.value = true;
      try {
        var res = await props.api.post('plugin/' + pluginId + '/history/clear', {});
        if (res && res.success) {
          showSnack('已清空', 'success');
          await fetchData();
          selectedRecord.value = null;
        } else {
          showSnack(res && res.message || '清空失败', 'error');
        }
      } catch (e) {
        showSnack('清空请求失败', 'error');
      }
      clearing.value = false;
    }

    function showSnack(text, color) {
      snackbar.text = text;
      snackbar.color = color || 'success';
      snackbar.show = true;
    }

    onMounted(function() { fetchData(); });

    return function(_ctx, _cache) {
      var _component_v_icon = _resolveComponent("v-icon");
      var _component_v_btn = _resolveComponent("v-btn");
      var _component_v_btn_group = _resolveComponent("v-btn-group");
      var _component_v_chip = _resolveComponent("v-chip");
      var _component_v_progress_circular = _resolveComponent("v-progress-circular");
      var _component_v_snackbar = _resolveComponent("v-snackbar");

      var children = [];

      // Topbar (same as Page component)
      var topbarRight = [];
      topbarRight.push(_createVNode(_component_v_btn_group, { variant: "tonal", density: "compact", class: "elevation-0" }, {
        default: _withCtx(function() { return [
          _createVNode(_component_v_btn, { color: "primary", onClick: testSend, loading: sending.value, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_icon, { icon: "mdi-send", size: "18", class: "mr-sm-1" }),
              _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "测试")
            ]; })
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, { color: "primary", onClick: clearHistory, loading: clearing.value, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_icon, { icon: "mdi-delete-sweep", size: "18", class: "mr-sm-1" }),
              _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "清空")
            ]; })
          }, 8, ["loading"])
        ]; })
      }));

      var topbarSub;
      if (stats.last_run) {
        topbarSub = _createElementVNode("div", { class: "sc3-topbar__sub" }, " 上次发送：" + _toDisplayString(stats.last_run));
      } else {
        topbarSub = _createElementVNode("div", { class: "sc3-topbar__sub" }, "从未发送");
      }

      children.push(_createElementVNode("div", { class: "sc3-topbar" }, [
        _createElementVNode("div", { class: "sc3-topbar__left" }, [
          _createElementVNode("div", { class: "sc3-topbar__icon" }, [
            _createVNode(_component_v_icon, { icon: "mdi-bell-ring", size: "24" })
          ]),
          _createElementVNode("div", null, [
            _createElementVNode("div", { class: "sc3-topbar__title" }, "Server酱³ 消息通知"),
            topbarSub
          ])
        ]),
        _createElementVNode("div", { class: "sc3-topbar__right", style: { padding: "2px" } }, topbarRight)
      ]));

      // Stats cards (same as Page)
      var s = stats;
      children.push(_createElementVNode("div", { class: "sc3-results" }, [
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--status" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "运行状态"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(s.enabled ? '已启用' : '未启用'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--uid" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "SendKey"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(s.has_sendkey ? '已配置' : '未配置'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--types" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "消息类型数"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(s.msgtype_count || '全部'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--count" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "发送记录"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(s.history_count))
        ])
      ]));

      // Latest record card
      if (selectedRecord.value) {
        var lr = selectedRecord.value;
        var lrStatusClass = lr.success ? "sc3-badge sc3-badge--success" : "sc3-badge sc3-badge--error";
        var lrStatusText = lr.success ? '成功' : '失败';
        children.push(_createElementVNode("div", { class: "sc3-latest" }, [
          _createElementVNode("div", { class: "sc3-latest__header" }, [
            _createVNode(_component_v_icon, { icon: "mdi-bell-ring", size: "16", color: "primary", class: "mr-1" }),
            _createElementVNode("span", null, "最新推送"),
            _createElementVNode("span", { class: "sc3-latest__time" }, _toDisplayString(lr.time)),
            _createVNode(_component_v_btn, {
              icon: "mdi-delete",
              size: "x-small",
              variant: "text",
              color: "grey",
              class: "sc3-latest__delete",
              onClick: function(t) { return function() { deleteRecord(t); }; }(lr.time)
            })
          ]),
          _createElementVNode("div", { class: "sc3-latest__body" }, [
            _createElementVNode("div", { class: "sc3-latest__title" }, _toDisplayString(lr.title || '(无标题)')),
            lr.text ? _createElementVNode("div", { class: "sc3-latest__text" }, _toDisplayString(lr.text)) : null,
            _createElementVNode("div", { class: "sc3-latest__meta" }, [
              _createElementVNode("span", { class: lrStatusClass }, _toDisplayString(lrStatusText)),
              _createElementVNode("span", { class: "sc3-latest__type" }, _toDisplayString(lr.msg_type || '-')),
              lr.error ? _createElementVNode("span", { class: "sc3-latest__error" }, _toDisplayString(lr.error)) : null
            ])
          ])
        ]));
      }

      // History section (same as Page)
      if (history.value.length > 0) {
        var rows = [];
        for (var i = 0; i < pagedHistory.value.length; i++) {
          var row = pagedHistory.value[i];
          var rowClass = i % 2 === 1 ? "sc3-table__row--alt" : "";
          var isSelected = selectedRecord.value && selectedRecord.value.time === row.time;
          var trClass = rowClass + (isSelected ? " sc3-table__row--selected" : "");
          var textPreview = row.text ? row.text.substring(0, 60) + (row.text.length > 60 ? '...' : '') : '-';
          var statusClass = row.success ? "sc3-badge sc3-badge--success" : "sc3-badge sc3-badge--error";
          var statusText = row.success ? '成功' : '失败';
          rows.push(_createElementVNode("tr", {
            class: trClass,
            onClick: function(r) { return function() {
              selectedRecord.value = r;
            }; }(row)
          }, [
            _createElementVNode("td", { class: "sc3-table__time" }, _toDisplayString(row.time)),
            _createElementVNode("td", { class: "sc3-table__title" }, _toDisplayString(row.title || '(无标题)')),
            _createElementVNode("td", null, [
              _createElementVNode("span", { class: statusClass }, _toDisplayString(statusText))
            ]),
            _createElementVNode("td", { class: "sc3-table__type" }, _toDisplayString(row.msg_type || '-')),
            _createElementVNode("td", { class: "sc3-table__text" }, _toDisplayString(textPreview)),
            _createElementVNode("td", { class: "sc3-table__error" }, _toDisplayString(row.error || '-')),
            _createElementVNode("td", { class: "sc3-table__action" }, [
              _createVNode(_component_v_btn, {
                icon: "mdi-delete",
                size: "x-small",
                variant: "text",
                color: "grey",
                onClick: function(t) { return function() { deleteRecord(t); }; }(row.time)
              })
            ])
          ]));
        }

        var pagination = null;
        if (totalPages.value > 1) {
          pagination = _createElementVNode("div", { class: "sc3-pagination" }, [
            _createElementVNode("button", { class: "sc3-pg-btn", disabled: page.value <= 1, onClick: function() { page.value--; } }, "‹"),
            _createElementVNode("span", { class: "sc3-pg-info" }, _toDisplayString(page.value) + " / " + _toDisplayString(totalPages.value)),
            _createElementVNode("button", { class: "sc3-pg-btn", disabled: page.value >= totalPages.value, onClick: function() { page.value++; } }, "›")
          ]);
        }

        children.push(_createElementVNode("div", { class: "sc3-card" }, [
          _createElementVNode("div", { class: "sc3-card__header" }, [
            _createElementVNode("span", { class: "sc3-card__title" }, "📋 发送记录"),
            _createElementVNode("span", { class: "sc3-card__header-right" }, [
              _createVNode(_component_v_btn, {
                icon: "mdi-delete-sweep",
                size: "x-small",
                variant: "text",
                color: "error",
                onClick: clearHistory
              }),
              _createElementVNode("span", { class: "sc3-card__badge" }, _toDisplayString(historyTotal.value) + " 条")
            ])
          ]),
          _createElementVNode("div", { class: "sc3-table-wrap" }, [
            _createElementVNode("table", { class: "sc3-table" }, [
              _createElementVNode("thead", null, [
                _createElementVNode("tr", null, [
                  _createElementVNode("th", null, "时间"),
                  _createElementVNode("th", null, "标题"),
                  _createElementVNode("th", null, "状态"),
                  _createElementVNode("th", null, "类型"),
                  _createElementVNode("th", null, "内容"),
                  _createElementVNode("th", null, "错误信息"),
                  _createElementVNode("th", { class: "sc3-table__th-action" }, "操作")
                ])
              ]),
              _createElementVNode("tbody", null, rows)
            ])
          ]),
          pagination
        ]));
      } else {
        children.push(_createElementVNode("div", { class: "sc3-no-data" }, [
          _createElementVNode("span", null, "暂无发送记录")
        ]));
      }

      // Snackbar
      children.push(_createVNode(_component_v_snackbar, {
        modelValue: snackbar.show,
        "onUpdate:modelValue": function($event) { snackbar.show = $event; },
        color: snackbar.color,
        timeout: "2500",
        location: "top"
      }, {
        default: _withCtx(function() { return [_createTextVNode(_toDisplayString(snackbar.text))]; })
      }, 8, ["modelValue", "color"]));

      return _createElementVNode("div", null, children);
    };
  }
});

export default _sfc_main;

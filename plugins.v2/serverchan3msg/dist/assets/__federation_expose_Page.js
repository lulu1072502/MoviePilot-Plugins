import { importShared } from './__federation_fn_import.js';

const { defineComponent: _defineComponent } = await importShared('vue');

const { resolveComponent: _resolveComponent, createVNode: _createVNode, createElementVNode: _createElementVNode, toDisplayString: _toDisplayString, openBlock: _openBlock, createElementBlock: _createElementBlock, createCommentVNode: _createCommentVNode, withCtx: _withCtx, createTextVNode: _createTextVNode, renderList: _renderList, Fragment: _Fragment, normalizeClass: _normalizeClass } = await importShared('vue');

const { ref, reactive, computed, onMounted } = await importShared('vue');

const pageSize = 10;

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    pluginId: String,
    api: { type: Object, default: () => ({}) }
  },
  emits: ["action", "switch", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const pluginId = props.pluginId || 'ServerChan3Msg';

    const stats = reactive({
      enabled: false,
      has_sendkey: false,
      msgtype_count: 0,
      sendkey_preview: '',
      history_count: 0,
      last_run: null
    });

    const history = ref([]);
    const historyTotal = ref(0);
    const latest = ref(null);
    const selectedRecord = ref(null);
    const expanded = ref(false);
    const page = ref(1);
    const sending = ref(false);
    const loading = reactive({ history: false });
    const snackbar = reactive({ show: false, text: '', color: 'success' });

    const pagedHistory = computed(function() {
      var start = (page.value - 1) * pageSize;
      return history.value.slice(start, start + pageSize);
    });

    const totalPages = computed(function() {
      return Math.ceil(history.value.length / pageSize);
    });

    async function fetchStats() {
      try {
        var res = await props.api.get('plugin/' + pluginId + '/stats');
        if (res) {
          stats.enabled = res.enabled || false;
          stats.has_sendkey = res.has_sendkey || false;
          stats.msgtype_count = res.msgtype_count || 0;
          stats.sendkey_preview = res.sendkey_preview || '';
          stats.history_count = res.history_count || 0;
          if (history.value.length > 0) {
            stats.last_run = history.value[0].time;
          }
        }
      } catch (e) {
        console.warn('[SC3] Stats error:', e);
      }
    }

    async function fetchHistory() {
      loading.history = true;
      try {
        var res = await props.api.get('plugin/' + pluginId + '/history?page=1&page_size=999');
        if (res && res.items) {
          history.value = res.items;
          historyTotal.value = res.total;
          page.value = 1;
          if (res.items.length > 0) {
            stats.last_run = res.items[0].time;
          }
        }
      } catch (e) {
        console.warn('[SC3] History error:', e);
      } finally {
        loading.history = false;
      }
    }

    async function fetchLatest() {
      try {
        var res = await props.api.get('plugin/' + pluginId + '/latest');
        if (res && res.has_data) {
          latest.value = res.record;
          if (!selectedRecord.value) selectedRecord.value = res.record;
        } else {
          latest.value = null;
          if (!selectedRecord.value) selectedRecord.value = null;
        }
      } catch (e) {
        console.warn('[SC3] Latest error:', e);
      }
    }

    async function testSend() {
      if (sending.value) return;
      sending.value = true;
      try {
        var res = await props.api.get('plugin/' + pluginId + '/test');
        if (res && res.success) {
          showSnack('测试消息发送成功', 'success');
        } else {
          showSnack(res && res.message || '发送失败', 'error');
        }
        await fetchHistory();
        await fetchStats();
        await fetchLatest();
        selectedRecord.value = history.value.length > 0 ? history.value[0] : null;
        emit('action');
      } catch (e) {
        showSnack('测试发送请求失败', 'error');
      } finally {
        sending.value = false;
      }
    }

    function showSnack(text, color) {
      snackbar.text = text;
      snackbar.color = color || 'success';
      snackbar.show = true;
    }

    async function deleteRecord(time) {
      try {
        var res = await props.api.post('plugin/' + pluginId + '/history/delete', { time: time });
        if (res && res.success) {
          showSnack('记录已删除', 'success');
          await fetchHistory();
          await fetchStats();
          await fetchLatest();
          if (selectedRecord.value && selectedRecord.value.time === time) {
            selectedRecord.value = history.value.length > 0 ? history.value[0] : null;
          }
          emit('action');
        } else {
          showSnack(res && res.message || '删除失败', 'error');
        }
      } catch (e) {
        showSnack('删除请求失败', 'error');
      }
    }

    async function clearHistory() {
      try {
        var res = await props.api.post('plugin/' + pluginId + '/history/clear', {});
        if (res && res.success) {
          showSnack('历史记录已清空', 'success');
          await fetchHistory();
          await fetchStats();
          await fetchLatest();
          emit('action');
        } else {
          showSnack(res && res.message || '清空失败', 'error');
        }
      } catch (e) {
        showSnack('清空请求失败', 'error');
      }
    }

    onMounted(async function() {
      await fetchStats();
      await fetchLatest();
      await fetchHistory();
    });

    return function(_ctx, _cache) {
      var _component_v_icon = _resolveComponent("v-icon");
      var _component_v_btn = _resolveComponent("v-btn");
      var _component_v_btn_group = _resolveComponent("v-btn-group");
      var _component_v_progress_circular = _resolveComponent("v-progress-circular");
      var _component_v_snackbar = _resolveComponent("v-snackbar");

      var children = [];

      // Topbar
      var topbarRight = [];
      topbarRight.push(_createVNode(_component_v_btn_group, { variant: "tonal", density: "compact", class: "elevation-0" }, {
        default: _withCtx(function() { return [
          _createVNode(_component_v_btn, { color: "primary", onClick: testSend, loading: sending.value, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_icon, { icon: "mdi-send", size: "18", class: "mr-sm-1" }),
              _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "测试")
            ]; })
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, { color: "primary", onClick: function($event) { emit("switch", "Config"); }, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_icon, { icon: "mdi-cog", size: "18", class: "mr-sm-1" }),
              _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "设置")
            ]; })
          }),
          _createVNode(_component_v_btn, { color: "primary", onClick: function($event) { emit("close"); }, size: "small", "min-width": "40", class: "px-0 px-sm-3" }, {
            default: _withCtx(function() { return [
              _createVNode(_component_v_icon, { icon: "mdi-close", size: "18" })
            ]; })
          })
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

      // Stats cards
      children.push(_createElementVNode("div", { class: "sc3-results" }, [
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--status" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "运行状态"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(stats.enabled ? '已启用' : '未启用'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--uid" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "SendKey"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(stats.has_sendkey ? '已配置' : '未配置'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--types" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "消息类型数"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(stats.msgtype_count || '全部'))
        ]),
        _createElementVNode("div", { class: "sc3-result-card sc3-result-card--count" }, [
          _createElementVNode("div", { class: "sc3-result-card__label" }, "发送记录"),
          _createElementVNode("div", { class: "sc3-result-card__value" }, _toDisplayString(stats.history_count))
        ])
      ]));

      // Selected record card
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

      // History section
      if (loading.history) {
        children.push(_createElementVNode("div", { class: "sc3-loading" }, [
          _createVNode(_component_v_progress_circular, { indeterminate: "", color: "primary" })
        ]));
      } else if (history.value.length > 0) {
        var rows = [];
        for (var i = 0; i < pagedHistory.value.length; i++) {
          var row = pagedHistory.value[i];
          var rowClass = i % 2 === 1 ? "sc3-table__row--alt" : "";
          var textPreview = row.text ? row.text.substring(0, 60) + (row.text.length > 60 ? '...' : '') : '-';
          var statusClass = row.success ? "sc3-badge sc3-badge--success" : "sc3-badge sc3-badge--error";
          var statusText = row.success ? '成功' : '失败';
          var isSelected = selectedRecord.value && selectedRecord.value.time === row.time;
          var trClass = rowClass + (isSelected ? " sc3-table__row--selected" : "");
          rows.push(_createElementVNode("tr", {
            class: trClass,
            onClick: function(r) { return function() {
              selectedRecord.value = r;
              expanded.value = false;
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
          _createElementVNode("span", null, '暂无发送记录')
        ]));
      }

      // Snackbar
      children.push(_createVNode(_component_v_snackbar, {
        modelValue: snackbar.show,
        "onUpdate:modelValue": function($event) { snackbar.show = $event; },
        color: snackbar.color,
        timeout: "3000",
        location: "top"
      }, {
        default: _withCtx(function() { return [
          _createTextVNode(_toDisplayString(snackbar.text))
        ]; })
      }, 8, ["modelValue", "color"]));

      return _createElementVNode("div", { class: "sc3-page" }, children);
    };
  }
});

export default _sfc_main;

import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class ServerChan3Msg(_PluginBase):
    """
    Server酱³ 消息通知插件。
    使用 Server酱³（方糖气球）API 发送推送通知到手机。
    """

    plugin_name = "Server酱³ 消息通知"
    plugin_desc = "支持使用 Server酱³（方糖气球）发送推送通知到手机。"
    plugin_icon = "https://ft07.com/favicon.ico"
    plugin_version = "2.1.0"
    plugin_author = "local"
    author_url = "https://github.com/easychen/serverchan3-doc"
    plugin_config_prefix = "serverchan3msg_"
    plugin_order = 31
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _clear_history = False
    _uid = None
    _sendkey = None
    _msgtypes = []
    _history = []
    _max_history = 50
    _history_limit = 50
    _show_sidebar = True
    _last_message_id = 0

    def init_plugin(self, config: dict = None) -> None:
        """
        根据插件配置初始化运行状态。
        """
        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._clear_history = config.get("clear_history", False)
            self._uid = config.get("uid", "")
            self._sendkey = config.get("sendkey", "")
            self._msgtypes = config.get("msgtypes") or []
            self._history_limit = int(config.get("history_limit", 50))
            self._show_sidebar = bool(config.get("show_sidebar", True))

        # 加载历史记录
        self._history = self.get_data("history") or []
        self._last_message_id = self.get_data("last_message_id") or 0

        # 清空历史记录
        if self._clear_history:
            self._history = []
            self.save_data("history", self._history)
            logger.info("Server酱³ 历史记录已清空")
            self._clear_history = False

        logger.info(f"Server酱³ 插件初始化: enabled={self._enabled}, uid={self._uid or '自动'}, "
                     f"sendkey={'已配置' if self._sendkey else '未配置'}, "
                     f"msgtypes={self._msgtypes}")

        if self._onlyonce:
            from app.schemas.types import NotificationType
            logger.info("Server酱³ 开始发送测试消息")
            flag = self.send_msg(
                title="Server酱³ 消息通知测试",
                text="Server酱³ 消息通知测试成功！",
                msg_type=NotificationType.Plugin,
            )
            if flag:
                self.systemmessage.put("Server酱³ 消息通知测试成功！")
                logger.info("Server酱³ 测试消息发送成功")
            else:
                logger.warn("Server酱³ 测试消息发送失败")
            self._onlyonce = False

        self.__update_config()

    def __update_config(self) -> None:
        """
        持久化当前配置。
        """
        config = {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "clear_history": self._clear_history,
            "uid": self._uid,
            "sendkey": self._sendkey,
            "msgtypes": self._msgtypes,
            "history_limit": self._history_limit,
            "show_sidebar": self._show_sidebar,
        }
        self.update_config(config)

    def get_state(self) -> bool:
        """
        获取插件启用状态。
        """
        return self._enabled and bool(self._sendkey)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        返回插件远程命令列表。
        """
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """
        返回插件 API 列表。
        """
        return [
            {
                "path": "/test",
                "endpoint": self.api_test_send,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "测试发送消息",
                "description": "手动触发一次消息发送测试",
            },
            {
                "path": "/stats",
                "endpoint": self.api_stats,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件统计信息",
                "description": "返回插件启用状态、SendKey 配置、消息类型数和发送记录数",
            },
            {
                "path": "/history",
                "endpoint": self.api_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取发送历史记录",
                "description": "分页返回发送历史记录列表",
            },
            {
                "path": "/config",
                "endpoint": self.api_get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取当前配置",
                "description": "返回插件当前配置",
            },
            {
                "path": "/config",
                "endpoint": self.api_save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置",
                "description": "保存插件配置并重新初始化",
            },
            {
                "path": "/history/delete",
                "endpoint": self.api_delete_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除单条历史记录",
                "description": "按时间戳删除单条发送记录",
            },
            {
                "path": "/history/clear",
                "endpoint": self.api_clear_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清空所有历史记录",
                "description": "删除全部发送记录",
            },
            {
                "path": "/latest",
                "endpoint": self.api_latest,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取最新发送记录",
                "description": "返回最近一条发送记录",
            },
        ]

    def api_stats(self) -> dict:
        """
        API: 获取插件统计信息。
        """
        return {
            "enabled": self._enabled,
            "has_sendkey": bool(self._sendkey),
            "msgtype_count": len(self._msgtypes),
            "sendkey_preview": self._sendkey[:12] + "..." if self._sendkey else None,
            "history_count": len(self._history),
        }

    def api_test_send(self) -> dict:
        """
        API: 手动触发测试发送。
        """
        from app.schemas.types import NotificationType
        logger.info("Server酱³ API 测试发送")
        flag = self.send_msg(
            title="Server酱³ API 测试",
            text="通过 API 触发的测试消息",
            msg_type=NotificationType.Plugin,
        )
        return {"success": flag, "message": "发送成功" if flag else "发送失败"}

    def api_history(self, page: int = 1, page_size: int = 10) -> dict:
        """
        API: 获取发送历史记录（分页）。
        """
        total = len(self._history)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        items = self._history[start:end]
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "items": items,
        }

    def api_get_config(self) -> dict:
        """
        API: 获取当前配置。
        """
        return {
            "enabled": self._enabled,
            "onlyonce": False,
            "clear_history": False,
            "uid": self._uid or "",
            "sendkey": self._sendkey or "",
            "msgtypes": self._msgtypes or [],
            "history_limit": self._history_limit,
            "show_sidebar": self._show_sidebar,
        }

    def api_save_config(self, payload: dict = None) -> dict:
        """
        API: 保存配置。
        """
        if not payload:
            return {"success": False, "message": "参数为空"}
        try:
            new_config = {
                "enabled": bool(payload.get("enabled", self._enabled)),
                "onlyonce": bool(payload.get("onlyonce", False)),
                "clear_history": bool(payload.get("clear_history", False)),
                "uid": payload.get("uid", self._uid or ""),
                "sendkey": payload.get("sendkey", self._sendkey or ""),
                "msgtypes": payload.get("msgtypes", self._msgtypes or []),
                "history_limit": int(payload.get("history_limit", self._history_limit)),
                "show_sidebar": bool(payload.get("show_sidebar", self._show_sidebar)),
            }
            self.init_plugin(new_config)
            self.update_config(new_config)
            return {"success": True, "message": "配置已保存"}
        except Exception as e:
            logger.error(f"Server酱³ 保存配置失败: {e}")
            return {"success": False, "message": str(e)}

    def api_delete_history(self, payload: dict = None) -> dict:
        """
        API: 删除单条历史记录。
        """
        if not payload or not payload.get("time"):
            return {"success": False, "message": "参数为空"}
        try:
            time_str = payload.get("time")
            new_history = [h for h in self._history if h.get("time") != time_str]
            if len(new_history) == len(self._history):
                return {"success": False, "message": "未找到该记录"}
            self._history = new_history
            self.save_data("history", self._history)
            logger.info(f"Server酱³ 已删除记录: {time_str}")
            return {"success": True, "message": "记录已删除"}
        except Exception as e:
            logger.error(f"Server酱³ 删除记录失败: {e}")
            return {"success": False, "message": str(e)}

    def api_clear_history(self) -> dict:
        """
        API: 清空所有历史记录。
        """
        try:
            self._history = []
            self.save_data("history", self._history)
            logger.info("Server酱³ 已清空所有历史记录")
            return {"success": True, "message": "历史记录已清空"}
        except Exception as e:
            logger.error(f"Server酱³ 清空记录失败: {e}")
            return {"success": False, "message": str(e)}

    def api_latest(self) -> dict:
        """
        API: 获取最新发送记录。
        """
        if self._history:
            return {"has_data": True, "record": self._history[0]}
        return {"has_data": False, "record": None}

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        """
        返回 Vue 渲染模式，使用 Vue 联邦组件渲染插件 UI。
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """
        Vue 模式下返回空表单和默认配置。
        """
        return [], self.api_get_config()

    def get_page(self) -> List[dict]:
        """
        Vue 模式下详情页由远程 Page 组件渲染。
        """
        return []

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        """
        返回侧栏导航项。
        """
        if not self._show_sidebar:
            return []
        return [
            {
                "nav_key": "main",
                "title": "Server酱³",
                "icon": "mdi-bell-ring",
                "section": "start",
                "permission": "manage",
                "order": 10,
            }
        ]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        返回仪表盘元数据列表。
        """
        return [
            {"key": "overview", "name": "发送概览"},
        ]

    def get_dashboard(
        self, key: str = "", **kwargs: Any,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]:
        """
        按 key 返回仪表盘栅格配置、标题和组件列表。
        """
        _ = kwargs
        k = (key or "").strip()

        if k == "overview":
            enabled_text = "已启用" if self._enabled else "未启用"
            sendkey_text = "已配置" if self._sendkey else "未配置"
            msgtype_text = str(len(self._msgtypes)) if self._msgtypes else "全部"
            history_count = len(self._history)
            return (
                {"cols": 12, "sm": 6, "md": 4, "lg": 3},
                {
                    "title": "发送概览",
                    "subtitle": "",
                    "border": True,
                    "dashboard_key": "overview",
                },
                [
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "pa-4"},
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {"component": "div", "props": {"class": "text-body-2 text-grey"}, "text": "运行状态"},
                                            {"component": "div", "props": {"class": "text-h6"}, "text": enabled_text}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {"component": "div", "props": {"class": "text-body-2 text-grey"}, "text": "SendKey"},
                                            {"component": "div", "props": {"class": "text-h6"}, "text": sendkey_text}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {"component": "div", "props": {"class": "text-body-2 text-grey"}, "text": "消息类型"},
                                            {"component": "div", "props": {"class": "text-h6"}, "text": msgtype_text}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {"component": "div", "props": {"class": "text-body-2 text-grey"}, "text": "发送记录"},
                                            {"component": "div", "props": {"class": "text-h6"}, "text": str(history_count)}
                                        ]
                                    },
                                ]
                            }
                        ]
                    }
                ],
            )

        if k == "latest":
            latest_record = self._history[0] if self._history else None
            if not latest_record:
                return (
                    {"cols": 12, "sm": 6, "md": 4, "lg": 3},
                    {
                        "title": "推送概览",
                        "subtitle": "",
                        "border": True,
                        "dashboard_key": "latest",
                    },
                    [
                        {
                            "component": "VCard",
                            "props": {"variant": "outlined", "class": "pa-6 text-center"},
                            "content": [
                                {"component": "div", "props": {"class": "text-body-1 text-grey"}, "text": "暂无发送记录"}
                            ]
                        }
                    ],
                )

            success = latest_record.get("success", False)
            status_text = "成功" if success else "失败"
            status_color = "success" if success else "error"
            title = latest_record.get("title", "") or "(无标题)"
            text = latest_record.get("text", "") or ""
            msg_type = latest_record.get("msg_type", "") or "-"
            error_text = latest_record.get("error", "") or ""
            time_str = latest_record.get("time", "")

            content = [
                {
                    "component": "VCard",
                    "props": {"variant": "outlined", "class": "pa-4"},
                    "content": [
                        {
                            "component": "div",
                            "props": {"class": "d-flex align-center mb-2"},
                            "content": [
                                {"component": "div", "props": {"class": "text-body-2 text-grey flex-grow-1"}, "text": time_str},
                                {
                                    "component": "VChip",
                                    "props": {"color": status_color, "size": "small"},
                                    "text": status_text
                                },
                                {
                                    "component": "VChip",
                                    "props": {"size": "small", "variant": "outlined", "class": "ml-1"},
                                    "text": msg_type
                                }
                            ]
                        },
                        {"component": "div", "props": {"class": "text-body-1 font-weight-medium mb-1"}, "text": title},
                    ]
                }
            ]

            if text:
                content[0]["content"].append(
                    {
                        "component": "div",
                        "props": {
                            "class": "text-body-2",
                            "style": "white-space: pre-wrap; word-break: break-word; line-height: 1.6; max-height: 80px; overflow-y: auto;"
                        },
                        "text": text[:300] + ("..." if len(text) > 300 else "")
                    }
                )

            if error_text:
                content[0]["content"].append(
                    {
                        "component": "VAlert",
                        "props": {"type": "error", "density": "compact", "variant": "tonal", "class": "mt-2"},
                        "content": [
                            {"component": "div", "props": {"class": "text-body-2"}, "text": error_text}
                        ]
                    }
                )

            return (
                {"cols": 12, "sm": 6, "md": 8, "lg": 9},
                {
                    "title": "推送概览",
                    "subtitle": "",
                    "border": True,
                    "dashboard_key": "latest",
                },
                content,
            )

        return (
            {"cols": 12},
            {
                "title": "发送概览",
                "subtitle": "",
                "border": True,
            },
            None,
        )

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event) -> None:
        """
        消息发送事件处理。
        """
        if not self.get_state():
            logger.info("Server酱³ 插件未启用或 SendKey 未配置，跳过消息发送")
            return

        if not event.event_data:
            return

        msg_body = event.event_data
        # 渠道
        channel = msg_body.get("channel")
        if channel:
            logger.info(f"Server酱³ 收到渠道消息，跳过: channel={channel}")
            return
        # 类型
        msg_type: NotificationType = msg_body.get("type")
        # 标题
        title = msg_body.get("title")
        # 文本
        text = msg_body.get("text")
        # 图片
        image = msg_body.get("image")

        if not title and not text:
            logger.warn("Server酱³ 标题和内容不能同时为空")
            return

        if msg_type and self._msgtypes is not None:
            # 空列表表示过滤所有消息类型
            # 兼容 .name（如 Download）和 .value（如 资源下载）两种格式
            if not self._msgtypes or (msg_type.name not in self._msgtypes and msg_type.value not in self._msgtypes):
                logger.info(f"Server酱³ 消息类型 {msg_type.value} 未开启消息发送")
                return

        logger.info(f"Server酱³ 准备发送消息: title={title}, type={msg_type.value if msg_type else '未知'}")
        self.send_msg(title=title, text=text, image=image, msg_type=msg_type)

    def send_msg(self, title: str, text: str, image: str = None, msg_type: NotificationType = None) -> bool:
        """
        发送消息到 Server酱³。

        Args:
            title: 消息标题。
            text: 消息正文。
            image: 可选图片 URL。
            msg_type: 消息类型，用于设置 tags。

        Returns:
            发送成功返回 True，否则返回 False。
        """
        if not self._sendkey:
            logger.error("Server酱³ SendKey 未配置")
            return False

        # 优先使用配置中的 uid，未配置则从 SendKey 提取
        uid = self._uid
        if not uid:
            uid_match = re.match(r"^sctp(\d+)t", self._sendkey)
            if uid_match:
                uid = uid_match.group(1)
                logger.info(f"Server酱³ 从 SendKey 提取 UID: {uid}")
            else:
                logger.error(f"Server酱³ SendKey 格式无效，且未配置 UID: {self._sendkey}")
                return False

        url = f"https://{uid}.push.ft07.com/send/{self._sendkey}.send"
        logger.info(f"Server酱³ 请求 API: https://{uid}.push.ft07.com/send/***.send")

        # 构建正文内容
        content = text or ""
        if image:
            content += f"\n![image]({image})"

        data = {
            "title": title,
            "desp": content,
        }

        # 根据消息类型设置 tags
        if msg_type:
            data["tags"] = msg_type.value

        try:
            res = RequestUtils().post_res(url=url, data=data)

            if res:
                ret_json = res.json()
                errno = ret_json.get("code")
                error = ret_json.get("message")
                if errno == 0:
                    logger.info("Server酱³ 消息发送成功")
                    self.__save_history(True, title, text, msg_type, None)
                    return True
                else:
                    logger.error(f"Server酱³ 消息发送失败：{error}")
                    self.__save_history(False, title, text, msg_type, error)
                    return False
            elif res is not None:
                err_msg = f"错误码：{res.status_code}，错误原因：{res.reason}"
                logger.error(f"Server酱³ 消息发送失败，{err_msg}")
                self.__save_history(False, title, text, msg_type, err_msg)
                return False
            else:
                logger.error("Server酱³ 消息发送失败：未获取到返回信息")
                self.__save_history(False, title, text, msg_type, "未获取到返回信息")
                return False
        except Exception as msg_e:
            logger.error(f"Server酱³ 消息发送失败 - {str(msg_e)}")
            self.__save_history(False, title, text, msg_type, str(msg_e))
            return False

    def __save_history(self, success: bool, title: str, text: str,
                       msg_type: NotificationType = None, error: str = None) -> None:
        """
        保存发送记录到历史数据。

        Args:
            success: 是否发送成功。
            title: 消息标题。
            text: 消息正文。
            msg_type: 消息类型。
            error: 错误信息。
        """
        import datetime
        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "title": title,
            "text": text[:500] if text else "",
            "msg_type": msg_type.value if msg_type else "",
            "error": error or "",
        }
        self._history.insert(0, record)
        # 限制最大记录数
        if len(self._history) > self._history_limit:
            self._history = self._history[:self._history_limit]
        self.save_data("history", self._history)

    def stop_service(self) -> None:
        """
        停止插件后台服务并释放资源。
        """
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册定时服务，定期检查消息历史并发送通知。
        """
        if not self.get_state():
            return []
        return [
            {
                "id": "serverchan3msg_poll",
                "name": "Server酱³ 消息检查",
                "trigger": "interval",
                "interval": 15,
                "func": self.__check_new_messages,
                "kwargs": {},
            }
        ]

    def __check_new_messages(self) -> None:
        """
        定期检查是否有新消息需要发送。
        从数据库 message 表中读取未发送的 Web 消息。
        """
        if not self.get_state():
            return
        try:
            from app.db.message_oper import MessageOper
            from app.db import get_db

            db_session = next(get_db())
            try:
                oper = MessageOper(db_session)
                # 获取最近的消息（按 ID 降序）
                messages = oper.list_by_page(page=1, count=100) or []
            finally:
                db_session.close()

            if not isinstance(messages, list):
                return
            for msg in messages:
                msg_id = msg.id or 0
                if msg_id <= self._last_message_id:
                    continue
                mtype = msg.mtype
                title = msg.title or ""
                text = msg.text or ""
                channel = msg.channel
                if channel:
                    continue
                if not title and not text:
                    continue
                if mtype and self._msgtypes is not None:
                    if not self._msgtypes or (mtype not in self._msgtypes):
                        continue
                self.send_msg(title=title, text=text)
                self._last_message_id = msg_id
                self.save_data("last_message_id", self._last_message_id)
        except Exception as e:
            logger.error(f"Server酱³ 消息检查失败: {e}")

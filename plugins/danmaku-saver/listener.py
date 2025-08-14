# -*- coding: utf-8 -*-
import __main__
import datetime
import json
import logging
import os
import sqlite3
import sys
from typing import *

import blcsdk
import blcsdk.models as sdk_models
import config

logger = logging.getLogger('danmaku-saver.' + __name__)

_msg_handler: Optional['MsgHandler'] = None
_id_room_dict: Dict[int, 'Room'] = {}


async def init():
    global _msg_handler
    _msg_handler = MsgHandler()
    blcsdk.set_msg_handler(_msg_handler)

    # 初始化数据库
    init_database()

    # 创建已有的房间
    try:
        blc_rooms = await blcsdk.get_rooms()
        for blc_room in blc_rooms:
            if blc_room.room_id is not None:
                _get_or_add_room(blc_room.room_id)
    except blcsdk.SdkError:
        pass


def init_database():
    """初始化SQLite数据库"""
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    
    # 创建弹幕表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS danmaku (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL,
        msg_type TEXT NOT NULL,
        author_name TEXT NOT NULL,
        content TEXT,
        timestamp DATETIME NOT NULL,
        raw_data TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()


def shut_down():
    blcsdk.set_msg_handler(None)
    while len(_id_room_dict) != 0:
        room_id = next(iter(_id_room_dict))
        _del_room(room_id)


class MsgHandler(blcsdk.BaseHandler):
    def on_client_stopped(self, client: blcsdk.BlcPluginClient, exception: Optional[Exception]):
        logger.info('blivechat disconnected')
        __main__.start_shut_down()

    def _on_open_plugin_admin_ui(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.OpenPluginAdminUiMsg, extra: sdk_models.ExtraData
    ):
        if sys.platform == 'win32':
            os.startfile(config.DATA_PATH)
        else:
            logger.info('Data path is "%s"', config.DATA_PATH)

    def _on_room_init(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.RoomInitMsg, extra: sdk_models.ExtraData
    ):
        if extra.is_from_plugin:
            return
        if message.is_success:
            _get_or_add_room(extra.room_id)

    def _on_del_room(self, client: blcsdk.BlcPluginClient, message: sdk_models.DelRoomMsg, extra: sdk_models.ExtraData):
        if extra.is_from_plugin:
            return
        if extra.room_id is not None:
            _del_room(extra.room_id)

    def _on_add_text(self, client: blcsdk.BlcPluginClient, message: sdk_models.AddTextMsg, extra: sdk_models.ExtraData):
        if extra.is_from_plugin:
            return
        room = _get_or_add_room(extra.room_id)
        # 保存原始数据
        raw_data = {
            'type': 'text',
            'author_name': message.author_name,
            'content': message.content,
            'timestamp': datetime.datetime.now().isoformat()
        }
        room.save_danmaku('text', message.author_name, message.content, raw_data)

    def _on_add_gift(self, client: blcsdk.BlcPluginClient, message: sdk_models.AddGiftMsg, extra: sdk_models.ExtraData):
        if extra.is_from_plugin:
            return
        room = _get_or_add_room(extra.room_id)
        if message.total_coin != 0:
            content = (
                f'赠送了 {message.gift_name} x {message.num}，总价 {message.total_coin / 1000:.1f} 元'
            )
        else:
            content = (
                f'赠送了 {message.gift_name} x {message.num}，总价 {message.total_free_coin} 银瓜子'
            )
        # 保存原始数据
        raw_data = {
            'type': 'gift',
            'author_name': message.author_name,
            'gift_name': message.gift_name,
            'num': message.num,
            'total_coin': message.total_coin,
            'total_free_coin': message.total_free_coin,
            'content': content,
            'timestamp': datetime.datetime.now().isoformat()
        }
        room.save_danmaku('gift', message.author_name, content, raw_data)

    def _on_add_member(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.AddMemberMsg, extra: sdk_models.ExtraData
    ):
        if extra.is_from_plugin:
            return
        room = _get_or_add_room(extra.room_id)
        if message.privilege_type == sdk_models.GuardLevel.LV1:
            guard_name = '舰长'
        elif message.privilege_type == sdk_models.GuardLevel.LV2:
            guard_name = '提督'
        elif message.privilege_type == sdk_models.GuardLevel.LV3:
            guard_name = '总督'
        else:
            guard_name = '未知舰队等级'
        content = (
            f'购买了 {message.num}{message.unit} {guard_name}，总价 {message.total_coin / 1000:.1f} 元'
        )
        # 保存原始数据
        raw_data = {
            'type': 'member',
            'author_name': message.author_name,
            'privilege_type': message.privilege_type,
            'guard_name': guard_name,
            'num': message.num,
            'unit': message.unit,
            'total_coin': message.total_coin,
            'content': content,
            'timestamp': datetime.datetime.now().isoformat()
        }
        room.save_danmaku('member', message.author_name, content, raw_data)

    def _on_add_super_chat(
        self, client: blcsdk.BlcPluginClient, message: sdk_models.AddSuperChatMsg, extra: sdk_models.ExtraData
    ):
        if extra.is_from_plugin:
            return
        room = _get_or_add_room(extra.room_id)
        content = f'发送了 {message.price} 元的醒目留言：{message.content}'
        # 保存原始数据
        raw_data = {
            'type': 'superchat',
            'author_name': message.author_name,
            'price': message.price,
            'content': message.content,
            'timestamp': datetime.datetime.now().isoformat()
        }
        room.save_danmaku('superchat', message.author_name, content, raw_data)


def _get_or_add_room(room_id):
    room = _id_room_dict.get(room_id, None)
    if room is None:
        if room_id is None:
            raise TypeError('room_id is None')
        room = _id_room_dict[room_id] = Room(room_id)
    return room


def _del_room(room_id):
    room = _id_room_dict.pop(room_id, None)
    if room is not None:
        room.close()


class Room:
    def __init__(self, room_id):
        self.room_id = room_id
        self.danmaku_count = 0
        self.danmaku_list = []
        self.file_index = 0
        
        # 创建房间数据目录
        self.room_data_path = os.path.join(config.DATA_PATH, f'room_{room_id}')
        os.makedirs(self.room_data_path, exist_ok=True)

    def close(self):
        # 保存剩余的弹幕到文件
        if self.danmaku_list:
            self._save_to_file()

    def save_danmaku(self, msg_type, author_name, content, raw_data):
        """保存弹幕到数据库和文件"""
        # 保存到数据库
        self._save_to_database(msg_type, author_name, content, raw_data)
        
        # 添加到列表，准备保存到文件
        self.danmaku_list.append(raw_data)
        self.danmaku_count += 1
        
        # 每1000条保存一个文件
        if self.danmaku_count % 1000 == 0:
            self._save_to_file()

    def _save_to_database(self, msg_type, author_name, content, raw_data):
        """保存到SQLite数据库"""
        try:
            conn = sqlite3.connect(config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO danmaku (room_id, msg_type, author_name, content, timestamp, raw_data) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.room_id,
                    msg_type,
                    author_name,
                    content,
                    datetime.datetime.now().isoformat(),
                    json.dumps(raw_data)
                )
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f'Failed to save to database: {e}')

    def _save_to_file(self):
        """保存到JSON文件"""
        if not self.danmaku_list:
            return
        
        # 生成文件名
        cur_time = datetime.datetime.now()
        time_str = cur_time.strftime('%Y%m%d_%H%M%S')
        filename = f'danmaku_{self.file_index}_{time_str}.json'
        file_path = os.path.join(self.room_data_path, filename)
        
        # 保存到文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.danmaku_list, f, ensure_ascii=False, indent=2)
            logger.info(f'Saved {len(self.danmaku_list)} danmakus to {file_path}')
            
            # 重置列表和增加文件索引
            self.danmaku_list = []
            self.file_index += 1
        except Exception as e:
            logger.error(f'Failed to save to file: {e}')
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Shrimadhav U K

# the logging things
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import asyncio
import json
import math
import os
import shutil
import time
from datetime import datetime

# the secret configuration specific things
if bool(os.environ.get("WEBHOOK", False)):
    from sample_config import Config
else:
    from config import Config

# the Strings used for this "thing"
from translation import Translation

import pyrogram
logging.getLogger("pyrogram").setLevel(logging.WARNING)

from pyrogram.types import InputMediaPhoto
from helper_funcs.display_progress import progress_for_pyrogram, humanbytes
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from helper_funcs.help_Nekmo_ffmpeg import generate_screen_shots
from pyrogram.enums import ParseMode

async def youtube_dl_call_back(bot, update):
    cb_data = update.data
    # youtube_dl extractors
    tg_send_type, youtube_dl_format, youtube_dl_ext = cb_data.split("|")
    thumb_image_path = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id) + ".jpg"
    save_ytdl_json_path = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id) + ".json"
    
    try:
        with open(save_ytdl_json_path, "r", encoding="utf8") as f:
            response_json = json.load(f)
    except FileNotFoundError:
        await bot.delete_messages(
            chat_id=update.message.chat.id,
            message_ids=update.id,
            revoke=True
        )
        return False
    
    youtube_dl_url = update.message.reply_to_message.text
    custom_file_name = str(response_json.get("title")) + "_" + youtube_dl_format + "." + youtube_dl_ext
    youtube_dl_username = None
    youtube_dl_password = None
    
    if "|" in youtube_dl_url:
        url_parts = youtube_dl_url.split("|")
        if len(url_parts) == 2:
            youtube_dl_url = url_parts[0]
            custom_file_name = url_parts[1]
        elif len(url_parts) == 4:
            youtube_dl_url = url_parts[0]
            custom_file_name = url_parts[1]
            youtube_dl_username = url_parts[2]
            youtube_dl_password = url_parts[3]
        else:
            for entity in update.message.reply_to_message.entities:
                if entity.type == "text_link":
                    youtube_dl_url = entity.url
                elif entity.type == "url":
                    o = entity.offset
                    l = entity.length
                    youtube_dl_url = youtube_dl_url[o:o + l]

        if youtube_dl_url is not None:
            youtube_dl_url = youtube_dl_url.strip()
        if custom_file_name is not None:
            custom_file_name = custom_file_name.strip()
        if youtube_dl_username is not None:
            youtube_dl_username = youtube_dl_username.strip()
        if youtube_dl_password is not None:
            youtube_dl_password = youtube_dl_password.strip()
        
        logger.info(youtube_dl_url)
        logger.info(custom_file_name)
    else:
        for entity in update.message.reply_to_message.entities:
            if entity.type == "text_link":
                youtube_dl_url = entity.url
            elif entity.type == "url":
                o = entity.offset
                l = entity.length
                youtube_dl_url = youtube_dl_url[o:o + l]

    await bot.edit_message_text(
        text=Translation.DOWNLOAD_START,
        chat_id=update.message.chat.id,
        message_id=update.message.id
    )
    
    user = await bot.get_me()
    mention = user.mention
    description = Translation.CUSTOM_CAPTION_UL_FILE.format(mention)
    
    if "fulltitle" in response_json:
        description = response_json["fulltitle"][0:1021]

    tmp_directory_for_each_user = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id)
    
    if not os.path.isdir(tmp_directory_for_each_user):
        os.makedirs(tmp_directory_for_each_user)

    download_directory = tmp_directory_for_each_user + "/" + custom_file_name
    
    command_to_exec = []
    
    if tg_send_type == "audio":
        command_to_exec = [
            "yt-dlp",
            "-c",
            "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
            "--prefer-ffmpeg",
            "--extract-audio",
            "--audio-format", youtube_dl_ext,
            "--audio-quality", youtube_dl_format,
            youtube_dl_url,
            "-o", download_directory
        ]
    else:
        minus_f_format = youtube_dl_format
        
        if "youtu" in youtube_dl_url:
            minus_f_format += "+bestaudio"
        
        command_to_exec = [
            "yt-dlp",
            "-c",
            "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
            "--embed-subs",
            "-f", minus_f_format,
            "--hls-prefer-ffmpeg", 
            youtube_dl_url,
            "-o", download_directory
        ]
    
    if Config.HTTP_PROXY != "":
        command_to_exec.append("--proxy")
        command_to_exec.append(Config.HTTP_PROXY)
    
    if youtube_dl_username is not None:
        command_to_exec.append("--username")
        command_to_exec.append(youtube_dl_username)
    
    if youtube_dl_password is not None:
        command_to_exec.append("--password")
        command_to_exec.append(youtube_dl_password)
    
    command_to_exec.append("--no-warnings")
    
    logger.info(command_to_exec)
    
    start = datetime.now()
    
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    stdout, stderr = await process.communicate()
    
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    
    logger.info(e_response)
    logger.info(t_response)

    ad_string_to_replace = ("please report this issue on https://yt-dl.org/bug . Make sure you are using "
                             "the latest version; see  https://yt-dl.org/update  on how to update. Be sure to call "
                             "youtube-dl with the --verbose flag and include its complete output.")
                             
    if e_response and ad_string_to_replace in e_response:
        error_message = e_response.replace(ad_string_to_replace, "")
        
        await bot.edit_message_text(
            chat_id=update.message.chat.id,
            message_id=update.message.id,
            text=error_message
        )
        
        return False
    
    if t_response:
        if os.path.exists(save_ytdl_json_path):
            os.remove(save_ytdl_json_path)
        else:
            logger.warning(f"{save_ytdl_json_path} does not exist, unable to remove.")
        
        end_one = datetime.now()
        
        time_taken_for_download = (end_one - start).seconds
        
        file_size = Config.TG_MAX_FILE_SIZE + 1
        
        try:
            file_size = os.stat(download_directory).st_size
        except FileNotFoundError:
            download_directory = os.path.splitext(download_directory)[0] + ".mkv"
            file_size = os.stat(download_directory).st_size
        
        logger.info(f"Download completed in {time_taken_for_download} seconds, file size: {humanbytes(file_size)}")

        if file_size > Config.TG_MAX_FILE_SIZE:
            await bot.edit_message_text(
                chat_id=update.message.chat.id,
                text=Translation.RCHD_TG_API_LIMIT.format(time_taken_for_download, humanbytes(file_size)),
                message_id=update.message.id
            )
            
            is_w_f = False
            
            images = await generate_screen_shots(
                download_directory,
                tmp_directory_for_each_user,
                is_w_f,
                Config.DEF_WATER_MARK_FILE,
                300,
                9
            )
            
            logger.info(images)
            
            await bot.edit_message_text(
                text=Translation.UPLOAD_START,
                chat_id=update.message.chat.id,
                message_id=update.message.id
            )
            
            width, height, duration = 0, 0, 0
            
            if tg_send_type != "file":
                metadata = extractMetadata(createParser(download_directory))
                
                if metadata is not None and metadata.has("duration"):
                    duration = metadata.get('duration').seconds
            
            if os.path.exists(thumb_image_path):
                metadata_thumb_image_path = extractMetadata(createParser(thumb_image_path))
                
                if metadata_thumb_image_path.has("width"):
                    width = metadata_thumb_image_path.get("width")
                
                if metadata_thumb_image_path.has("height"):
                    height = metadata_thumb_image_path.get("height")
                
                if tg_send_type == "vm":
                    height = width
                
                Image.open(thumb_image_path).convert("RGB").save(thumb_image_path)
                
                img = Image.open(thumb_image_path)

                if tg_send_type == "file":
                    img.resize((320, height))
                else:
                    img.resize((90, height))
                    
                img.save(thumb_image_path, "JPEG")
                
            else:
                thumb_image_path = None
            
            start_time = time.time()
            
            # Try to upload file based on type.
            send_method_mapping = {
                'audio': bot.send_audio,
                'file': bot.send_document,
                'vm': bot.send_video_note,
                'video': bot.send_video,
            }
            
            send_method_args_mapping = {
                'audio': {'audio': download_directory, 'caption': description, 'parse_mode': ParseMode.HTML, 'duration': duration},
                'file': {'document': download_directory, 'thumb': thumb_image_path, 'caption': description, 'parse_mode': ParseMode.HTML},
                'vm': {'video_note': download_directory, 'duration': duration, 'length': width, 'thumb': thumb_image_path},
                'video': {'video': download_directory, 'caption': description, 'parse_mode': ParseMode.HTML, 'duration': duration, 'width': width, 'height': height},
           }
           
           send_method_args_mapping[tg_send_type].update({
               'reply_to_message_id': update.message.reply_to_message.id,
               'progress': progress_for_pyrogram,
               'progress_args': (Translation.UPLOAD_START, update.message, start_time),
           })
           
           await send_method_mapping[tg_send_type](chat_id=update.message.chat.id, **send_method_args_mapping[tg_send_type])
           
           end_two = datetime.now()
           time_taken_for_upload = (end_two - end_one).seconds

           media_album_p=[]
           caption="© @LazyDeveloperr"
           
           for i,image in enumerate(images):
               media_album_p.append(InputMediaPhoto(media=image, caption=(caption if i==0 else ""), parse_mode=ParseMode.HTML))
           
           await bot.send_media_group(
               chat_id=update.message.chat.id,
               disable_notification=True,
               reply_to_message_id=update.id,
               media=media_album_p
           )

           try:
               shutil.rmtree(tmp_directory_for_each_user)
               os.remove(thumb_image_path)
           except Exception as e:
               logger.error(f"Error cleaning up temporary files: {e}")

           await bot.edit_message_text(
               text=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download, time_taken_for_upload),
               chat_id=update.message.chat.id,
               message_id=update.message.id,
               disable_web_page_preview=True
          )

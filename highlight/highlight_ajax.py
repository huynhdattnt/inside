# -*- coding: utf-8 -*-

from flask import Blueprint, redirect, request, json, url_for, jsonify, current_app
from flask.ext.login import current_user
from flaskext.babel import gettext as _
from datetime import datetime
from inside.extensions import db, app, video_permission_list, cache
from inside.utils import get_user_role, check_file_exist, log_activity, slugify_filename, call_mobifone_iapi
from inside.views.helper.video_helper import check_structure_and_priority_video
from slugify import slugify
from unidecode import unidecode
from mongokit import ObjectId
import json
import os
import requests


highlight_ajax = Blueprint('highlight_ajax', __name__, url_prefix='/highlight')

@highlight_ajax.route('/publish', methods=['PUT'])
def publish_highlight():
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        hl_id           = request.json['hl_id']
        if hl_id:
            old_obj     = db.HighlightItem.get_by_id(hl_id) #used for logging
            #change publish to 1
            result = db.HighlightItem.publish_highlight(hl_id)
            if not result:
                return jsonify(result=int(0), _id=hl_id, msg="publish %s fail due to some error with executing db query" % hl_id)

            new_obj     = db.HighlightItem.get_by_id(hl_id) #used for logging
            #logging
            log_activity(old_obj, new_obj, 'highlight', 'update', 'update highlight', 'publish highlight')

            return jsonify(result=int(1), _id=hl_id, msg="%s highlight is published" % hl_id)

        return jsonify(result=int(0), _id='none', msg="no highlight id")
    return 'permission denied', 403

@highlight_ajax.route('/unpublish', methods=['PUT'])
def unpublish_highlight():
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        hl_id           = request.json['hl_id']
        if hl_id:
            old_obj     = db.HighlightItem.get_by_id(hl_id) #used for logging
            #change publish to 0
            result = db.HighlightItem.unpublish_highlight(hl_id)
            if not result:
                return jsonify(result=int(0), _id=hl_id, msg="unpublish %s fail due to some error with executing db query" % hl_id)

            new_obj     = db.HighlightItem.get_by_id(hl_id) #used for logging
            #logging
            log_activity(old_obj, new_obj, 'highlight', 'update', 'update highlight', 'unpublish highlight')

            return jsonify(result=int(1), _id=hl_id, msg="%s highlight is unpublished" % hl_id)

        return jsonify(result=int(0), _id=hl_id, msg="no highlight id")
    return 'permission denied', 403


@highlight_ajax.route('/change_priority', methods=['PUT'])
def change_priority():
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        structure_id    = request.json['structure_id']
        hl_id           = request.json['hl_id']
        new_priority    = request.json['new_priority']
        if hl_id and structure_id and new_priority:
            #change priority
            result = db.HighlightItem.change_priority(structure_id, hl_id, new_priority)
            if not result:
                return jsonify(result=int(0), msg="not found structure: '%s' in priority dict " % structure_id)
            return jsonify(result=int(1), msg="%s highlight index change to %s success" % (hl_id, new_priority))

        return jsonify(result=int(0), msg="no structure_id or highlight id or new_priority")
    return 'permission denied', 403

@highlight_ajax.route('/upload_event_img', methods=['POST'])
def upload_event_img():
    today = datetime.now().strftime("%d_%m_%Y")
    savepath = os.path.join(app.config['UPLOAD_EVENT_IMAGE_FOLDER'], today)
    file = request.files['imgFile']
    if not os.path.exists(savepath):
        os.mkdir(savepath)
    #slugify filename
    safe_filename = slugify_filename(file.filename, 'yes', 'yes')

    savepath = savepath + '/' + safe_filename
    file.save(savepath)
    status = 'DONE'
    img_link = today + '/' + safe_filename

    #validate image dimension
    #im=Image.open(savepath)
    #if im.size!=(356,200):
    #    status = 'fail'

    #logging
    log_activity(None, None, 'image', 'upload', 'upload image', 'upload highlight image %s' % savepath)

    return jsonify(result=status, img_link=img_link)

@highlight_ajax.route('/upload_vod_img', methods=['POST'])
def upload_vod_img():
    today = datetime.now().strftime("%d_%m_%Y")
    vid_savepath = os.path.join(app.config['UPLOAD_VIDEO_THUMBNAIL'], today)
    file1 = request.files['imgFile2']
    if not os.path.exists(vid_savepath):
        os.mkdir(vid_savepath)
    #slugify filename
    now_time      = datetime.now().strftime("%d-%m-%Y_%Hg%M-%S")
    safe_filename = slugify_filename(file1.filename, 'yes', 'yes')

    savepath = vid_savepath + '/' + safe_filename
    file1.save(savepath)
    status = 'DONE'
    img_link = today + '/' + safe_filename

    #logging
    log_activity(None, None, 'image', 'upload', 'upload image', 'upload highlight image %s' % savepath)
    #validate image dimension
    #im=Image.open(savepath)
    #if im.size!=(356,200):
    #    status = 'fail'

    return jsonify(result=status, img_link=img_link)

@highlight_ajax.route('/del', methods=['DELETE'])
def delete():
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        highlight_id = request.json['highlight_id']
        if not highlight_id:
            return 'no highlight_id'

        old_obj = db.HighlightItem.get_by_id(highlight_id) #use for logging

        #check priority video structure when delete
        for p in old_obj.priority:
            #decrease structure priority ralation
            db.HighlightItem.change_value_structure_in_priority(p,old_obj.priority[p],-1)

        #delete video object by id
        db.HighlightItem.remove_by_id(highlight_id)

        #logging
        log_activity(old_obj, old_obj, 'highlight', 'delete', 'delete highlight', 'delete highlight')


        return "Done"
    return 'permission denied', 403


@highlight_ajax.route('/reset_index', methods=['POST'])
def reset_index():
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        structure_id    = request.json['structure_id']
        if not structure_id:
            return jsonify(result=int(0), msg="No structure_id.")

        struc_obj       = db.Structure.get_by_id(structure_id)
        if not struc_obj:
            return jsonify(result=int(0), msg="Found no structure with inputted id: %s" % structure_id)

        if struc_obj['children']:
            return jsonify(result=int(0), msg="Structure %s still got children structures, cannot reset." % struc_obj['name'])

        #the order will be vod on, tv, vod off with the sorting of startime for tv and old index for vod
        #so we will create 3 different array to satisfy above order
        vod_on_list = db.HighlightItem.get_all_by_type_struc_publish_and_sort(type='vod', structure_id=structure_id, publish=1, field_sort='priority.%s'%structure_id, sort_way=1)
        vod_off_list= db.HighlightItem.get_all_by_type_struc_publish_and_sort(type='vod', structure_id=structure_id, publish=0, field_sort='priority.%s'%structure_id, sort_way=1)
        tv_list     = db.HighlightItem.get_all_by_type_struc_publish_and_sort(type='livetv', structure_id=structure_id, publish=None, field_sort='livetv_content.start_time', sort_way=1)

        #break tvlist into 2, 1 is not happening, one is the past
        now = datetime.now()
        tv1_list    = []
        tv2_list    = []
        for h in tv_list:
            if h['livetv_content']['end_time']>=now:
                tv1_list.append(h)
            else:
                tv2_list.append(h)

        new_order   = [h1 for h1 in vod_on_list] + [h2 for h2 in tv1_list] + [h25 for h25 in tv2_list] + [h3 for h3 in vod_off_list]
        index   = int(1)
        for h in new_order:
            print 'hl_id:', str(h['_id'])
            print 'index:', index
            #set priority
            result  = db.HighlightItem.hard_set_priority(structure_id, str(h['_id']), index)
            if not result:
                return jsonify(result=int(0), msg="Update highlight_id: %s to index %s fail" % (h['_id'], index) )
            index  += int(1)

        #logging
        log_activity(None, None, 'highlight', 'reset index', 'reset highlight index', 'reset highlight index')

        return jsonify(result=int(1), msg="Highlight index reset success.")

        return jsonify(result=int(0), msg="no structure_id or highlight id or new_priority")
    return 'permission denied', 403


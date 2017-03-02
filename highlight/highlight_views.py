# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, make_response, current_app, redirect, request, url_for, flash, jsonify
from inside.extensions import db, app, video_permission_list
from inside.forms import HighlightItemForm
from inside.utils import get_user_role, log_activity, slugify_filename, slugit, Pagination
from inside.views.helper.highlight_helper import check_platform_n_publish_country, check_structure_and_priority_video,\
                                        set_structure_id_choice, check_set_appointment_tv_event, cancel_appointment_highlight_off_task
from mongokit import ObjectId
from datetime import datetime, timedelta
import os

highlight_views = Blueprint('highlight_views', __name__, url_prefix='/highlight')

@highlight_views.route('/')
@highlight_views.route('/<int:page>', methods=['GET'])
def index(page=1):
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        search_str  = request.values.get('search_str') if request.values.get('search_str') else ''
        structure_id= request.values.get('structure_id')
        per_page    = request.values.get('per_page')

        per_page    = int(50) if not per_page else int(per_page)
        children_list   = []
        if not structure_id:
            #get the top structure for highlight type
            query     = db.Structure.get_by_exact_layer_and_type(1, 'highlights')
            if query:
                structure_id    = str(query['_id'])
        if structure_id:
            children_list = db.Structure.get_sorted_children_id(structure_id)

        #===============get highlight list===============
        #make structure dictionary
        structure_list  = db.Structure.get_all()
        struc_dict      = {}
        for s in structure_list:
            struc_dict[str(s['_id'])] = s.name

        #get list highlight sort by priority
        query = db.HighlightItem.get_by_structure_sort_pagi(structure_id, search_str, "priority."+structure_id if structure_id else '', 1, page, per_page)
        highlight_list = [v for v in query['result_list']]
        for i in range(0, len(highlight_list)):
            #get structure's name instead of id in highlight's infos
            structure_name = []
            for s in highlight_list[i]['structure_id']:
                if s in struc_dict:
                    structure_name.append(struc_dict[s])
            highlight_list[i]['structure_id']  = structure_name
            #check if this highlight got priority for this structure or not. If not, set default ''
            highlight_list[i]['priority'] = highlight_list[i]['priority'][structure_id] if structure_id in highlight_list[i]['priority'] else ''

        #for rendering pages bar
        total_item  = query['result_count']
        pagi        = Pagination(page, per_page, total_item)
        #================================================

        #create parent list for selected structure
        parent_path     = []
        section_list    = db.Structure.get_to_load_data_tree(['highlights'])
        #parent_dict is a dictionary that cotent parent path for earch structureId
        parent_dict     = {}
        #dictionary to be use in getting infos associate with structure_id
        structure_info      = {}
        if section_list:
            #init parent_dict
            for x in range(len(section_list[0])):
                parent_dict[str(section_list[0][x]['_id'])] = []
                #case structure_id = None. Standing at top tree. get all vod category layer 1 for children_list
                if not structure_id:
                    children_list.append(section_list[0][x])
            if not structure_id:
                #sorting the children list
                children_list = sorted(children_list, key=lambda k: k['priority'])
                children_list = [str(s['_id']) for s in children_list]
        #scan through each structure, create parent path associate with children id
        for layer in section_list:
            for item in layer:
                #set structure_name dictionary
                structure_info[str(item['_id'])] = item

                #case this item is selected structure
                if str(item['_id'])==structure_id:
                    parent_path   = parent_dict[str(item['_id'])]
                temp = []
                temp.extend(parent_dict[str(item['_id'])])
                temp.append(str(item['_id']))
                for c in item['children']:
                    parent_dict[str(c)] = temp

        #get all platforms for select options
        platforms = db.Platform.get_all()
        #get all geoip available for select options
        geoip_list = ['VN', 'REST_OF_THE_WORLD']

        return render_template('highlight/highlight_index.html', search_str=search_str, highlight_list=highlight_list,\
                pagi=pagi, platforms=platforms, geoip_list=geoip_list, structure_id=structure_id,\
                parent_path=parent_path, children_list=children_list, structure_info=structure_info, user_role=user_role, app=app)

    return 'permission denied', 403

@highlight_views.route('/edit', methods=['GET', 'POST'])
@highlight_views.route('/edit/<string:highlight_id>', methods=['GET', 'POST'])
def edit(highlight_id=None):
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        if not highlight_id:
            return redirect(url_for("highlight_views.index"))

        hl_obj      = db.HighlightItem.get_by_id(highlight_id)
        old_obj     = db.HighlightItem.get_by_id(highlight_id) #use for logging
        form        = HighlightItemForm(request.form, obj=hl_obj) #init highlight form
        if request.method == 'POST':
            form.populate_obj(hl_obj) #Populates the attributes of the passed obj with data from the form’s fields
            #------------------manually validating fields------------------------
            if len(hl_obj.structure_id) == 0:
                flash("You must select atleast 1 structure for this highlight!", "fail")
                return redirect(url_for("highlight_views.index"))
            #check available platform and GEOIP_COUNTRY_CODE_availability base on its parent structure
            check_platform_n_publish_country(hl_obj)

            #check priority highlight structure when save
            check_structure_and_priority_video(hl_obj)
            #--------------------------------------------------------------------

            #check if the type is livetv, the highlight should auto turn off after the endtime of event. Call iapi to do the appointment
            if hl_obj.livetv_content.end_time!=old_obj.livetv_content.end_time or old_obj.type!='livetv':
                #revoke old task
                cancel_appointment_highlight_off_task(old_obj)
                #set new task
                check_set_appointment_tv_event(hl_obj)

            hl_obj.save()

            #logging
            log_activity(old_obj, hl_obj, 'highlight', 'update', 'update highlight', 'update a highlight')

            flash("Highlight has been edited!", "success")
            return redirect(url_for("highlight_views.index", structure_id=hl_obj.structure_id[0]))

        #get choices for structure select box
        set_structure_id_choice(form, hl_obj.structure_id)
        #get choices for platforms field
        platforms = db.Platform.get_all()
        form.platform.choices   = [(p.type, p.type) for p in platforms]

        return render_template('highlight/highlight_newedit.html',form=form, hl_obj=hl_obj, highlight_id=highlight_id,\
                            user_role=user_role, current_app=current_app)

    return 'permission denied', 403

@highlight_views.route('/new', methods=['GET', 'POST'])
@highlight_views.route('/new/<string:structure_id>', methods=['GET','POST'])
def new(structure_id=None):
    #get user's role
    user_role = get_user_role()

    if user_role in video_permission_list:
        hl_obj              = db.HighlightItem()
        hl_obj['_id']       = ObjectId()

        #set default for platforms and geoip attribute
        platforms           = db.Platform.get_all()
        p_default           = []
        p_choices           = []
        for p in platforms:
            p_default.append(p.type)
            p_choices.append((p.type, p.type))
        hl_obj.type         = 'vod' #set default to vod
        hl_obj.platform     = p_default
        hl_obj.GEOIP_COUNTRY_CODE_availability  = ['VN', 'REST_OF_THE_WORLD']
        #set default image_type
        hl_obj.image_type   = 'standing_image' if structure_id=='55c42f6417dc1344d5012f5a' else 'small_image'
        hl_obj.publish      = int(1)

        form        = HighlightItemForm(request.form, obj=hl_obj) #init highlight form
        if request.method == 'POST':
            form.populate_obj(hl_obj) #Populates the attributes of the passed obj with data from the form’s fields
            #------------------manually validating fields------------------------
            if len(hl_obj.structure_id) == 0:
                flash("You must select atleast 1 structure for this highlight!", "fail")
                return redirect(url_for("highlight_views.index"))
            #check available platform and GEOIP_COUNTRY_CODE_availability base on its parent structure
            check_platform_n_publish_country(hl_obj)

            #check priority highlight structure when save
            check_structure_and_priority_video(hl_obj)
            #--------------------------------------------------------------------

            #check if the type is livetv, the highlight should auto turn off after the endtime of event. Call iapi to do the appointment
            check_set_appointment_tv_event(hl_obj)

            hl_obj.save()

            #logging
            log_activity(hl_obj, hl_obj, 'highlight', 'add', 'add highlight', 'add a highlight')

            flash("Highlight has been added!", "success")
            return redirect(url_for("highlight_views.index", structure_id=hl_obj.structure_id[0]))

        #get choices for structure select box
        set_structure_id_choice(form, [structure_id])
        #get choices for platform select box
        form.platform.choices   = p_choices

        return render_template('highlight/highlight_newedit.html',form=form, hl_obj=hl_obj, user_role=user_role, current_app=current_app)

    return 'permission denied', 403
#!/usr/bin/env Python
# coding=utf-8
import time
from datetime import datetime

from django.core.urlresolvers import reverse
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse

from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated
)
from rest_framework.decorators import (
    api_view,
    permission_classes,
    parser_classes,
)

from .serializers import *
from .constent import EPOCH


# Create your views here.
class JSONResponse(HttpResponse):
    """
    An HttpResponse that renders its content into JSON.
    """

    def __init__(self, data, **kwargs):
        content = JSONRenderer().render(data)
        kwargs['content_type'] = 'application/json'
        super(JSONResponse, self).__init__(content, **kwargs)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class APIRootView(APIView):
    def get(self, request):
        year = datetime.now().year
        data = {
            'year-summary-url': reverse('year-summary', args=[year], request=request)
        }
        return Response(data)


class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    ordering = ('-create_time')


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer


class ProcedureViewSet(viewsets.ModelViewSet):
    queryset = Procedure.objects.all()
    serializer_class = ProcedureSerializer


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def tags(request):
    data = []
    categorys = {}
    tags = Tag.objects.exclude(category__is_tag=1)
    if tags:
        for tag in tags:
            tag_id = tag.id
            tag_name = tag.name
            category_name = tag.category.name
            category_seq = tag.category.seq
            categroy = None
            if category_name in categorys:
                category = categorys[category_name]
            else:
                category = {'seq': category_seq, 'category': category_name, 'tags': []}
                categorys[category_name] = category
                data.append(category)
            category['tags'].append({
                'id': tag_id,
                'tag': tag_name,
            })

        if len(data) > 1:
            for item in range(0, len(data) - 1):
                # category_seq = data[item].get('seq')
                min = item
                for item2 in range(item + 1, len(data)):
                    if data[item2].get('seq') < data[min].get('seq'):
                        min = item2
                tmp = data[item]
                data[item] = data[min]
                data[min] = tmp
            return Response(data, status=status.HTTP_200_OK)
        else:
            return Response(data, status=status.HTTP_200_OK)
    else:
        return Response(data, status=status.HTTP_200_OK)


class RecipeResponseItem:
    def __init__(self, recipe, host, create_time,
                 tags):
        self.recipe = recipe
        self.host = host
        self.create_time = create_time
        self.tag = tags

    def to_data(self):
        recipe = self.recipe
        _id = recipe.id
        recipe_name = recipe.name
        user = recipe.user
        tips = recipe.tips
        introduce = recipe.introduce
        host = self.host
        url = 'http://%s/api/recipes/%d' % (host, _id)
        exihibitpic_url = recipe.exihibitpic
        exihibitpic = 'http://%s/images/%s' % (host, exihibitpic_url)
        exihibitpic = exihibitpic.decode('utf-8')
        data = {
            'id': _id,
            'url': url,
            'create_time': self.create_time,
            'recipe': recipe_name,
            'user': user,
            'tips': tips,
            'exihibitpic': exihibitpic,
            'introduce': introduce,
            'tag': self.tag
        }
        return data


class AgeTagManage:
    '''
    管理年龄tag
    '''
    def __init__(self):
        tag_query = Tag.objects.filter(category__is_tag=1)
        tags = tag_query.values_list('id', flat=True).all()
        self.tag_age_ids = set(tags)

    def check_age_query(self, tags):
        check_id = set(tags) & self.tag_age_ids
        return check_id

    def rest_age_tags(self, tag):
        return self.tag_age_ids - tag


class AgeQuery:
    def __init__(self, query, age_tag_id):
        self.query = query
        self.age_tag_id = age_tag_id


class RecipeDuplicationManager:
    '''
    删选结果
    '''
    def __init__(self):
        self.recipes = set()

    def add(self, recipe):
        self.recipes.add(recipe.id)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def recipe(request):
    '''
    参见: doc/api/: /api/recipe
    '''
    data = []
    search = request.data.get('search', None)
    create_time = request.data.get('create_time', None)
    tags_ = request.data.get('tag_id', [])
    host = request.META['HTTP_HOST']

    age_tag_manager = AgeTagManage()
    age_tag_id = age_tag_manager.check_age_query(tags_)

    rest_query_tags = tags_

    filter_dump_recipe = bool(tags_) #有查询就过滤

    if age_tag_id:
        query = Recipe.objects
        assert len(age_tag_id) == 1 #only one age id
        age_tag_id_ls = list(age_tag_id)
        age_id = age_tag_id_ls[0]
        query = query.filter(tag=age_tag_id_ls[0]) #age filter
        rest_query_tags = set(tags_) - age_tag_id
        querys = [AgeQuery(query, age_id)]
    else:
        querys = []
        for _age_tag_id in age_tag_manager.tag_age_ids: # 对所有年龄
            query = Recipe.objects
            query = query.filter(tag=_age_tag_id)
            querys.append(AgeQuery(query, _age_tag_id))

    # cache
    q = Q()
    for tag_id in rest_query_tags:
        q = q | Q(tag=tag_id)
    s = None
    if create_time:
        createtime = time.localtime(int(create_time))
        s = time.strftime('%Y-%m-%d %H:%M:%S', createtime)

    recipe_duplication_manager = RecipeDuplicationManager()

    for age_query in querys:
        query = age_query.query
        age_tag_id = age_query.age_tag_id
        query = query.filter(q)  # tag and query
        if search:
            query = query.filter(name__contains=search)
        if s:
            query = query.filter(create_time__gt=s)
        if filter_dump_recipe:
            query = query.exclude(id__in=list(recipe_duplication_manager.recipes))

        recipes = query.order_by('create_time')[:10]

        query_tag = Tag.objects.filter(id=age_tag_id)
        tag_first = query_tag[0]
        tag_name = tag_first.name
        tag_id = tag_first.id
        tag_seq = tag_first.seq

        tag = {'tag': tag_name, 'tag_id': tag_id, 'tag_seq': tag_seq, 'recipes': []}
        _recipes = []
        for recipe in recipes:
            recipe_duplication_manager.add(recipe)
            recipe_create_time = recipe.create_time

            td = recipe_create_time - EPOCH
            timestamp_recipe_createtime = int(td.microseconds + (td.seconds + td.days * 24 * 3600))

            _tags = [{"category_name": x.category.name, 'name': x.name}
                        for x in recipe.tag.filter(category__is_tag=4)]
            recipe_item = RecipeResponseItem(recipe=recipe,
                                             host=host,
                                             create_time=timestamp_recipe_createtime,
                                             tags=_tags)
            _recipes.append(recipe_item.to_data())
        if _recipes:
            tag['recipes'] = _recipes
            data.append(tag)
    data.sort(key=lambda x: x['tag_seq'])
    return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def reci(request):
    import pdb
    search = request.data.get('search', None)
    create_time = request.data.get('create_time', None)
    tags = request.data.get('tag_id', None)
    print tags

    def get_tag(tags=None):
        pdb.set_trace()
        if tags is not None:
            x = Tag.objects.filter(id__in=tags_)
            stage = [x.id for x in age]
            print stage
            print tags
            pdb.set_trace()
        else:
            return Tag.objects.none()
        print stage

    def get_recipe(tags_=None, serach=None, create_time=None):

        pass

    pdb.set_trace()

    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def tagshow(request):
    data = []
    categorys = {}
    tags = Tag.objects.filter(category__is_tag=1).order_by('seq')
    for tag in tags:
        tag_id = tag.id
        tag_name = tag.name
        tag_seq = tag.seq
        category_name = tag.category.name
        categroy = None
        if category_name in categorys:
            category = categorys[category_name]
        else:
            category = {'category': category_name, 'tags': []}
            categorys[category_name] = category
            data.append(category)
        category['tags'].append({
            'id': tag_id,
            'tag': tag_name,
            'is_tag': tag_seq
        })
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def recommend(request):
    # import pdb
    # pdb.set_trace()

    now = datetime.datetime.now()
    epoch = datetime.datetime(1970, 1, 1) + datetime.timedelta(hours=8)

    if Recommend.objects.all().filter(pubdate__lte=now):
        recommend = Recommend.objects.all().filter(pubdate__lte=now).order_by('-pubdate').first()

        if recommend.name:
            recommend_name = recommend.name
        else:
            recommend_name = recommend.recipe.name

        if recommend.introduce:
            recommend_introduce = recommend.introduce
        else:
            recommend_introduce = recommend.recipe.introduce

        recommend_image = recommend.image.url
        recommend_pubdate = recommend.pubdate
        recommend_create_time = recommend.create_time
        recommend_recipe_id = recommend.recipe.id
        recommend_recipe_create_time = recommend.recipe.create_time
        recommend_recipe_name = recommend.recipe.name
        recommend_recipe_user = recommend.recipe.user
        recommend_recipe_introduce = recommend.recipe.introduce

        td = recommend_recipe_create_time - epoch
        td1 = recommend_create_time - epoch
        td2 = recommend_pubdate - epoch
        timestamp_recipe_createtime = int(td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6)
        timestamp_createtime = int(td1.microseconds + (td1.seconds + td1.days * 24 * 3600) * 10 ** 6)
        timestamp_pubdate = int(td2.microseconds + (td2.seconds + td2.days * 24 * 3600) * 10 ** 6)

        recommend = {'recommend_recipe': 'Today\'s Specials', 'create_time': timestamp_createtime,
                     'pubdate': timestamp_pubdate, 'image': request.build_absolute_uri(recommend_image),
                     'name': recommend_name, 'introduce': recommend_introduce, 'recipe': {}}

        recommend['recipe'] = {
            'id': recommend_recipe_id,
            'create_time': timestamp_recipe_createtime,
            'name': recommend_recipe_name,
            'user': recommend_recipe_user,
            'introduce': recommend_recipe_introduce,
            'url': "http://" + request.META['HTTP_HOST'] + '/' + 'api' + '/' + 'recipes' + '/' + str(
                recommend_recipe_id)
        }
        return Response(recommend, status=status.HTTP_200_OK)

    else:
        recommend = {}
        return Response(recommend, status=status.HTTP_200_OK)

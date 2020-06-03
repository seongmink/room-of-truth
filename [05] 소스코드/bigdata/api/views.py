from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework import status
from api.pagination import PaginationHandlerMixin
from rest_framework.pagination import PageNumberPagination
from api import models, serializers

# import os
# import sys
# import urllib.request
# import json
from django.db.models import Avg
from datetime import datetime
from django.db.models import Q
from django.db.models import Prefetch

class SmallPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class Contract(APIView, PaginationHandlerMixin):
    pagination_class = SmallPagination
    serializer_class = serializers.ContractSerializer

    def get(self, request, format=None, *args, **kwargs):

        area = request.query_params.get("area",None)
      
        instance = models.Contract.objects.all()

        if area is not None:
            instance = instance.filter(address__contains=area)

        page = self.paginate_queryset(instance)
        if page is not None:
            serializer = self.get_paginated_response(self.serializer_class(page,
 many=True).data)
        else:
            serializer = self.serializer_class(instance, many=True)
            
        return Response(serializer.data, status=status.HTTP_200_OK)
        

class ContractChart(APIView):

    def get_object(self, id):
            bd = get_object_or_404(models.Contract, pk=id)
            return bd
    def getAgg(self, instance_addr, instance_emd, target,key):
        label = {'2019-04':0,'2019-05':1,'2019-06':2,'2019-07':3,'2019-08':4,'2019-09':5,'2019-10':6,'2019-11':7,'2019-12':8,'2020-01':9,'2020-02':10,'2020-03':11,'2020-04':12}
        # --
        result_addr = (instance_addr.filter(detail=key)
        .values_list('contract_date__year', 'contract_date__month','detail')
        .annotate(Avg(target))
        .order_by('contract_date__year', 'contract_date__month'))
        addrs = [None]*13
        for r in result_addr:
            m=str(r[1])
            if r[1]<10:
                m = "0"+m
            m = str(r[0])+'-'+m
            addrs[label[m]]=round(r[-1],2)
        # --
        result_emd = (instance_emd.filter(detail=key)
        .values_list('contract_date__year', 'contract_date__month','detail')
        .annotate(Avg(target))
        .order_by('contract_date__year', 'contract_date__month'))
        emds = [None] * 13
        for r in result_emd:
            m=str(r[1])
            if r[1]<10:
                m = "0"+m
            m = str(r[0])+'-'+m
            emds[label[m]]=round(r[-1],2)
        return addrs, emds

    def get(self, request, pk):
        bd = self.get_object(pk)
        detail = request.query_params.get("detail",None)
        if detail is None:
            return Response("detail을 mm(매매),js(전세),ws(월세) 중 하나를 입력해주세요",status=status.HTTP_400_BAD_REQUEST)
        else: # detail 값이 있는 경우
            address = bd.address # 도로명주소
            sgg = bd.sgg # 시군구
            emd = bd.emd # 읍면동
            instance_addr = models.Contract.objects.all().filter(address=address)
            instance_emd = models.Contract.objects.all().filter(sgg=sgg).filter(emd=emd)
            keywords = {"js":"전세", "ws":"월세","mm":"매매"}
            if detail in keywords:
                key = keywords[detail] # 입력받은 타입
                addrs, emds = self.getAgg(instance_addr, instance_emd, "cost", key)
                if key=='월세': # 월세의 경우 보증금도 같이 연산해서 줘야함
                    m_addrs, m_emds = self.getAgg(instance_addr, instance_emd, "monthly", key)
                    return_value = {
                        'road_address':address,
                        'dong_address':sgg+" "+emd,
                        'label' : ['2019-04','2019-05','2019-06','2019-07','2019-08','2019-09','2019-10','2019-11','2019-12','2020-01','2020-02','2020-03','2020-04'],
                        'datatype': key,
                        'dong_data' :emds,
                        'addr_data':addrs,
                        'ws_dong_data':m_emds,
                        'ws_addr_data':m_addrs,
                    }
                else:
                    return_value = {
                        'road_address':address,
                        'dong_address':sgg+" "+emd,
                        'label' : ['2019-04','2019-05','2019-06','2019-07','2019-08','2019-09','2019-10','2019-11','2019-12','2020-01','2020-02','2020-03','2020-04'],
                        'datatype': key,
                        'dong_data' :emds,
                        'addr_data':addrs
                    }

                return Response(return_value, status=status.HTTP_200_OK)
            else:
                return Response("mm(매매),js(전세),ws(월세) 중 하나를 입력해주세요",status=status.HTTP_400_BAD_REQUEST)


# 거래이력 아이디를 이용해서 around받아오기
class ContractAround(APIView):

    def get(self, request, pk):
        contract = get_object_or_404(models.Contract, pk=pk)
        # print(contract.address)
        instance = models.Around.objects.get(address=contract.address)
        serializer = serializers.AroundSerializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

# 로그인 하지않은 유저에게 보여줄 전체 상위 9개의 이력
class TotalRank(APIView):
    
    def get(self, request, format=None, *args, **kwargs):
        results = []
        favs = models.Favorite.objects.all().values_list('around').annotate(sc = Avg('score')).order_by('-sc')
        # print(favs[:9])
        for idx, f in enumerate(favs[:9]):
            arnd = models.Around.objects.get(pk=f[0])
            b = models.Contract.objects.filter(address=arnd.address).first()
            results.append({
                "rank":idx+1,
                "num" : arnd.around_id,
                "name" : arnd.address,
                "image": b.image,
                "latitude":b.latitude,
                "longitude":b.longitude
            })
        return Response(results, status=status.HTTP_200_OK)

# 나이대,성별, 카테고리에 따른 첫 화면 3개 선정
class Rank(APIView):
    def get(self, request, pk):
        by = request.query_params.get("by",None)
        if by is None:
            return Response("by={gender,age,cate} 입력해주세요", status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(models.User, pk=pk)
        interest = user.interest_user.get()

        if interest.sd =="세종특별자치시":
            addr = interest.sd
        else:
            addr = interest.sd + " "+interest.sgg
        # --------------------------------------------------------
        # 카테고리 분류
        if by=='cate':
            d = {'교통':'trans','마트/편의점':'comforts','교육시설':'education','의료시설':'medical','음식점/카페':'eatery','문화시설':'culture'}
            cate_user = d[interest.first]
            arounds = models.Around.objects.filter(address__contains=addr).order_by('-'+cate_user)[:9]
            result = []
            favs = models.Favorite.objects.filter(around__address__contains=addr)
            # print(favs) # 사용자 선호도에 따른 순위
            tmp = {}
            for c in arounds:
                tmp[c.around_id]=getattr(c,cate_user)*0.5 + getattr(c,d[interest.second])*0.3 + getattr(c,d[interest.third])*0.2
            calc_around = favs.values_list('around').annotate(sc = Avg('score')).order_by('-sc') # 평점순위
            for c in calc_around:
                if c[0] in tmp:
                    tmp[c[0]]+=c[1]/5
            calc_scores = {k: v for k, v in sorted(tmp.items(), key=lambda item: item[1], reverse=True)}
            idx=0
            for item in calc_scores:
                if idx==3:
                    break
                arnd = models.Around.objects.get(pk=item)
                b = models.Contract.objects.filter(address=arnd.address).first()
                print(models.Favorite.objects.filter(around=arnd).filter(user=user))
                fav = len(models.Favorite.objects.filter(around=arnd).filter(user=user))
                result.append({
                "num" : arnd.around_id,
                "name" : arnd.address,
                "image": b.image,
                "latitude":b.latitude,
                "longitude":b.longitude,
                "isLike": True if fav >=1 else False
                })
                idx+=1

            return Response(result, status = status.HTTP_200_OK)

        # --------------------------------------------------------
        # 연령대, 성별 분류
        elif by=='age':
            curr_year = datetime.today().year
            gen = ((curr_year - interest.birth+1)//10)*10 # 사용자의 연령대
            start = curr_year+1-gen
            end = start-9
            # print(str(start) +" ~ "+str(end))
            users = models.Interest.objects.filter(birth__gte=end).filter(birth__lte=start)
        elif by=='gender':
            users = models.Interest.objects.filter(gender=interest.gender)
        else:
            return Response("by={gender,age,cate} 입력해주세요", status=status.HTTP_400_BAD_REQUEST)
        
        q = Q()
        for u in users:
            q.add(Q(user=u.user_num), q.OR)
        instance = models.Favorite.objects.filter(q).order_by('around').filter(around__address__contains=addr)
        # print(instance)
        # print(str(instance.query))
        queryset = instance.values_list('around').annotate(sc = Avg('score')).order_by('-sc')
        result = []
        if len(queryset) <3:
            # TODO : 각 지역별로 관심해논게 3개 이상씩은 되어야함 T-T
            instance = models.Favorite.objects.all().order_by('around').filter(around__address__contains=addr)
            queryset = instance.values_list('around').annotate(sc = Avg('score')).order_by('-sc')
        for q in  queryset[:3]:
            arnd = models.Around.objects.get(pk=q[0])
            b = models.Contract.objects.filter(address=arnd.address).first()
            fav = len(models.Favorite.objects.filter(user=pk).filter(around=arnd))
            result.append({
                "num" : q[0],
                "name" : b.address,
                "latitude":b.latitude,
                "longitude":b.longitude,
                "image": b.image,
                "isLike": True if fav ==1 else False
            })

        return Response(result, status=status.HTTP_200_OK)


# 관심지역, 카테고리에 따른 리스트 보여주기(sort)
# 추천서비스 (가제)
class Prefer(APIView):

    def get(self, request, format=None, *args, **kwargs):

        sgg = request.query_params.get("sgg", None)
        sd = request.query_params.get("sd",None)
        cate = request.query_params.get("cate",None)

        cate_name = {"gt":"trans","mt":"comforts","ed":"education","md":"medical","fc":"eatery","ct":"culture"}
        if sd is None or cate is None or cate not in cate_name:
            return Response("값 입력 필요", status=  status.HTTP_400_BAD_REQUEST)
        if sd=="세종특별자치시":
            addr = sd
        else:
            if sgg is None:
                return Response("sgg 값 입력 필요", status=  status.HTTP_400_BAD_REQUEST)
            addr = sd+" "+sgg
        cat = cate_name[cate]
        instance = models.Around.objects.filter(address__contains=addr).order_by('-'+cat)
        results = []
        # TODO : 위도경도 줘야할까???
        for arnd in instance[:6]:
            addr = arnd.address
            b = models.Contract.objects.filter(address=addr).first()
            data = {
                "num":arnd.around_id,
                "name":arnd.address,
                "image":b.image,
                "longitude":b.longitude,
                "latitude":b.latitude,
                "trans":arnd.trans,
                "comforts":arnd.comforts,
                "education":arnd.education,
                "medical":arnd.medical,
                "eatery":arnd.eatery,
                "culture":arnd.culture
            }
            results.append(data)
            
        return Response(results, status=status.HTTP_200_OK)

    # TODO : 관심 지역에서 평가한 항목을 가지고 아이템(이력) 추천
class Recommend(APIView):

    def get(self, request, pk):
        user = get_object_or_404(models.User, pk=pk)
        results = []
            
        return Response(results, status=status.HTTP_200_OK)


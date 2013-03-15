from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied

from wq.db.patterns.models import Annotation, AnnotationType, Identifier

from wq.db.rest.models import get_ct, get_object_id, has_perm

RESERVED_PARAMETERS = ('_', 'page', 'limit', 'format')
_FORBIDDEN_RESPONSE = "Sorry %s, you do not have permission to %s this %s."

class View(generics.GenericAPIView):
    router = None

    @property
    def template_name(self):
        return type(self).__name__.replace('View', '').lower() + '.html'

    def get_template_names(self):
        return [self.template_name]

class InstanceModelView(View, generics.RetrieveUpdateDestroyAPIView):
    @property
    def template_name(self):
        return get_ct(self.model).identifier + '_detail.html'

    # FIXME: implement get_object (and get_slug_field?)
    def get_instance(self, *args, **kwargs):
        if get_ct(self.model).is_identified:
            return self.model.objects.get_by_identifier(kwargs['pk'])
        else:
            return super(InstanceModelView, self).get_instance(*args, **kwargs)
    
    # FIXME: these should be retrieve, update, destroy
    def get(self, request, *args, **kwargs):
        ct = get_ct(self.model)
        if not has_perm(request.user, ct, 'view'):
            forbid(request.user, ct, 'view')
        return super(InstanceModelView, self).get(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        ct = get_ct(self.model)
        if not has_perm(request.user, ct, 'change'):
            forbid(request.user, ct, 'change')

        res = super(InstanceModelView, self).put(request, *args, **kwargs)

        if ct.is_annotated:
            atypes = AnnotationType.objects.filter(contenttype=ct)
            for at in atypes:
                fname = 'annotation-%s' % at.pk
                if fname in self.CONTENT:
                    annot, isnew = Annotation.objects.get_or_create(
                        type=at, content_type=ct, object_id=res.pk)
                    annot.value = self.CONTENT[fname]
                    annot.save()
        return res

    def delete(self, request, *args, **kwargs):
        ct = get_ct(self.model)
        if not has_perm(request.user, ct, 'delete'):
            forbid(request.user, ct, 'delete')
        return super(InstanceModelView, delete).put(request, *args, **kwargs)

class ListOrCreateModelView(View, generics.ListCreateAPIView):
    annotations = None 
    parent = None

    @property
    def template_name(self):
        return get_ct(self.model).identifier + '_list.html'

    def get_query_kwargs(self, *args, **kwargs):
        for key, val in self.request.GET.items():
            if key in RESERVED_PARAMETERS:
                continue
            kwargs[key] = val if isinstance(val, unicode) else val[0]

        ctype = get_ct(self.model)
        for key, val in kwargs.items():
            if key in ('target',):
                del kwargs[key]
                continue
            found = False
            for f in self.model._meta.fields:
                if f.name != key and ctype.identifier + f.name != key:
                    continue
                found = True
                if getattr(f, 'rel', None):
                    del kwargs[key]
                    if get_ct(f.rel.to).is_identified:
                        kwargs[f.name] = f.rel.to.objects.get_by_identifier(val)
                    else:
                        kwargs[f.name] = f.rel.to.objects.get(pk=val)
                    self.parent = kwargs[f.name]

            if not found and ctype.is_related:
                for pct in ctype.get_all_parents():
                    if pct.identifier == key:
                        pclass = pct.model_class()
                        if pct.is_identified:
                            self.parent = pclass.objects.get_by_identifier(kwargs[key])
                        else:
                            self.parent = pclass.objects.get(pk=kwargs[key])
                        del kwargs[key]
                        objs = self.model.objects.filter_by_related(self.parent)
                        kwargs['pk__in'] = objs.values_list('pk', flat=True)
                
        kwargs = super(ListOrCreateModelView, self).get_query_kwargs(*args, **kwargs)
        return kwargs

    @property
    def CONTENT(self):
        content = super(ListOrCreateModelView, self).CONTENT
        ct = get_ct(self.model)
        if ct.is_annotated:
            atypes = AnnotationType.objects.filter(contenttype=ct)
            self.annotations = {}
            for at in atypes:
                fname = 'annotation-%s' % at.pk
                if fname in content:
                    self.annotations[at] = content[fname]
                    del content[fname]
        return content

    def get(self, request, *args, **kwargs):
        ct = get_ct(self.model)
        if not has_perm(request.user, ct, 'view'):
            forbid(request.user, ct, 'view')
        return super(ListOrCreateModelView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        ct = get_ct(self.model)
        if not has_perm(request.user, ct, 'add'):
            forbid(request.user, ct, 'add')
        res = super(ListOrCreateModelView, self).post(request, *args, **kwargs)

        if ct.is_annotated:
            for at, val in self.annotations.iteritems():
                annot, isnew = Annotation.objects.get_or_create(
                type=at, content_type=ct, object_id=res.raw_content.id)
                annot.value = val
                annot.save()
        return res

    def filter_response(self, obj):
        result = super(ListOrCreateModelView, self).filter_response(obj)
        if 'results' not in result:
            return result
        result['list'] = result['results']
        if 'list' in obj and 'pages' in obj:
            result['multiple'] = obj['pages'] > 1
        del result['results']
        if 'target' in self.kwargs:
            result['target'] = self.kwargs['target']
        if getattr(self, 'parent', None):
            result['parent_label'] = unicode(self.parent)
            result['parent_id']    = get_object_id(self.parent)
            result['parent_url']   = '%s/%s' % (
                get_ct(self.parent).urlbase, get_object_id(self.parent)
            )
        return result

def forbid(user, ct, perm):
    raise PermissionDenied(detail=_FORBIDDEN_RESPONSE % (user, perm, ct))

"""
Dokumentasi pengguna MQTT Client (tahap M13): /docs/, /docs/<slug>/, /docs/search/?q=...
Kerangka dan tampilan sama dengan dokumentasi IoT Platform. Bisa dibaca tanpa login.
"""
from django.http import Http404
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from . import pages, search
from .context import docs_context


def base_context(request, facts, current=None):
    """Menu bertingkat (bagian -> bab -> judul <h2> bab) dan kotak pencarian."""
    tocs = search.page_tocs(facts["http"]["base_url"], facts)
    nav = [
        (section, [{"page": item, "toc": tocs.get(item.slug, []), "current": item.slug == current}
                   for item in items])
        for section, items in pages.sections()
    ]
    return {"sections": pages.sections(), "nav": nav, "query": request.GET.get("q", "").strip()}


def index(request):
    return render(request, "userdocs/index.html", base_context(request, docs_context(request)))


def page(request, slug):
    doc = pages.BY_SLUG.get(slug)
    if doc is None:
        raise Http404("No such page.")
    facts = docs_context(request)
    context = dict(facts)
    rendered = render_to_string(doc.template, context, request=request)
    previous, following = pages.neighbours(slug)
    context.update(base_context(request, facts, current=slug))
    context.update({
        "doc": doc,
        "content": mark_safe(rendered),
        "toc": [item for item in search.toc(rendered) if item[0] in (2, 3)],
        "previous": previous,
        "following": following,
    })
    return render(request, "userdocs/page.html", context)


def search_view(request):
    facts = docs_context(request)
    context = base_context(request, facts)
    context["results"] = search.search(context["query"], facts["http"]["base_url"], facts)
    return render(request, "userdocs/search.html", context)

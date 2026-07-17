from .web_search import tavily_search

def get_custom_tools():
    return [tavily_search]
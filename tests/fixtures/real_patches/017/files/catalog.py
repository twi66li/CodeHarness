from paging import page

def list_items(items, number, size):
    return page(sorted(items, reverse=True), number, size)

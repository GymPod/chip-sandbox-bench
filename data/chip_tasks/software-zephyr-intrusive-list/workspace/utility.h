#include <stddef.h>
typedef struct list_node {struct list_node*prev,*next;} list_node_t;
void list_init(list_node_t*h); void list_append(list_node_t*h,list_node_t*n); void list_prepend(list_node_t*h,list_node_t*n);
void list_remove(list_node_t*n); list_node_t*list_pop_front(list_node_t*h); list_node_t*list_pop_back(list_node_t*h);

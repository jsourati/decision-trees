import numpy as np
import copy
import pdb
import fitting_tools

class Node:
    """
    Tree node: left and right child + data which can be any object
    """

    def __init__(self, key, dat, labels, is_stopped, reach_prob, class_prob,
                 rules=None, parent=None, left_child=None, right_child=None):
        """
        Node constructor
        
        left_child and right_child are integers. More specifically, they indicate
        indices (ID) of the children in terms of a vocabulary of nodes (dictionary
        of nodes). Same story holds for the parent
        """
        self.left = left_child
        self.right = right_child
        self.parent = parent
        self.rules = rules
        self.dat = dat
        self.labels = labels
        self.is_stopped = is_stopped
        self.reach_prob = reach_prob
        self.class_prob = class_prob
        
    def compute_error_rate(self):
        """Computing error rate of the node, based on the current posteriors
        """
        
        return 1 - max(self.class_prob)

class Tree(Node):
    """
    Tree class: it has a list of nodes, where the leaves are determined
    """
    
    def __init__(self, dat, labels, kernel_CDF):
        """
        Tree constructor: the objectives is a array of functions, each
        an objective to minimize over a single feature component
        """
        
        # the class priors (and symbols) are also the same for all the nodes, 
        #so compute it as a property of the tree (and not each node)
        # --------------------------------------
        c = len(np.unique(labels))
        is_stopped = True if c==1 else False
        class_info = np.zeros((2, c))
        class_info[0,:] = np.unique(labels)
        # comuting pies:
        for i in range(c):
            class_info[1,i] = np.sum(labels==class_info[0,i]) / float(len(labels))
        # --------------------------------------
        # now assigning the min-max (rules of the root) 
        if dat.ndim==1:
            a,b = (dat.min(), dat.max())
            rules = {'0': (a,b)}
        elif dat.ndim==2:
            a,b = np.min(dat, axis=1), np.max(dat, axis=1)
            rules = {}
            for i in range(len(a)):
                rules.update({str(i): (a[i], b[i])})
        else:
            raise ValueError('Dimension of the input data should not be higher than 2')
        # --------------------------------------
        # properties:
        self.node_dict = {'0': Node(0, dat, labels, is_stopped, 1., class_info[1,:], rules)}
        self.leaf_inds = [0]
        self.symbols = class_info[0,:]
        self.kernel_CDF = kernel_CDF
        
    
    def check_full_stopped(self):
        """
        Checking if all the leaves of the tree are stopped
        """

        for i in self.leaf_inds:
            leaf = self.node_dict[str(i)]
            if not(leaf.is_stopped):
                return False

        # if the For-loop is not broken, it means all the leaves are
        # stopped --> return true
        return True
    
    def fit_full_tree(self):
        """
        Method for fitting a full tree (a tree with maximum purity)
        from the root node. 
        
        Starting from the root node, we keep adding nodes until each
        leaf has samlpes with only a single unique class label.
        """
        
        # in order to give unique keys to the nodes, start by a value larger
        # than the existing keys in the node dictionary
        max_key = max(map(int, self.node_dict.keys()))
        
        # start adding children until full purity is obtained
        while not(self.check_full_stopped()):
            
            # go through all the leaves and split the non-stopped ones
            #leaf_list = copy.deepcopy(self.leaves)
            inds_to_remove = []
            inds_to_add    = []
            
            for i in self.leaf_inds:
                
                leaf = self.node_dict[str(i)]
                
                if not(leaf.is_stopped):
                    
                    # best splits:
                    thetas, scores = fitting_tools.split_features(leaf, self.kernel_CDF)
                    selected_feature = np.argmin(scores)
                    best_split = thetas[selected_feature]
                    
                    # creating the new left/right leaves
                    # ----------------------------------------
                    # priors and reachin probabilities
                    probs = fitting_tools.compute_probs_KDE(leaf, self.kernel_CDF, self.symbols, 
                                                            best_split, selected_feature)
                    left_priors, right_priors = probs[:2]
                    left_reach_prob = probs[2] * leaf.reach_prob
                    right_reach_prob = probs[3] * leaf.reach_prob
                    
                    # new rules:
                    left_rules, right_rules = fitting_tools.update_rules(best_split, selected_feature, leaf)
                    # new data
                    left_dat, left_labels = fitting_tools.filter_data(leaf.dat, leaf.labels, 
                                                        left_rules, selected_feature)
                    right_dat, right_labels = fitting_tools.filter_data(leaf.dat, leaf.labels, 
                                                          right_rules, selected_feature)
                    # stop the new leaves or not?
                    is_left_stopped = len(np.unique(left_labels))==1
                    is_right_stopped = len(np.unique(right_labels))==1
                    # children:
                    left_child = Node(max_key+1, left_dat, left_labels, is_left_stopped, 
                                      left_reach_prob, left_priors, rules=left_rules, parent=i)
                    right_child = Node(max_key+2, right_dat, right_labels, is_right_stopped, 
                                       right_reach_prob, right_priors, rules=right_rules, parent=i)
                    
                    # updating the tree structure
                    # ---------------------------
                    # mark the index of the current leaf to throw it out from the leaf-list
                    inds_to_remove += [i]
                    # add the new leaves into the leaf-list
                    self.node_dict.update({str(max_key+1): left_child, str(max_key+2): right_child})
                    inds_to_add += [max_key+1, max_key+2]
                    # add the new nodes as the children of the old leaf
                    leaf.left = max_key + 1
                    leaf.right = max_key + 2
                    
                    # update maximum key
                    max_key += 2
                    
            
            # updating the leaf list
            for j in inds_to_remove:
                self.leaf_inds.remove(j)
            self.leaf_inds += inds_to_add
            
            #pdb.set_trace()
        
    def total_misclass_rate(self):
        """Computing misclassification of the tree as the exected value of
        error rates of the leaves
        """
        
        misclass_rate = 0.
        for i in self.leaf_inds:
            leaf = self.node_dict[str(i)]
            misclass_rate += leaf.reach_prob * leaf.compute_error_rate()
        
        return misclass_rate
    
    def subtree_props(self, node_index):
        """Some properties of a subtree, including misclassification rate
        of the sub-tree and the list of its leaves (terminal nodes)
        
        The subtree is specified by its root, which is in turn, given by
        the index in the list of all nodes. Based on the notation from
        Breiman's book, the subtree is shown by :math:`T_t`.
        """
        
        if str(node_index) not in self.node_dict.keys():
            print 'Node %d is not a node of the tree..' % node_index
            return
        
        # initializing the subtree error rate
        sub_misclass_rate = 0.
        # node object of the sub-tree root
        sub_root = self.node_dict[str(node_index)]
        
        # check if the given root is a leaf itself
        if node_index in self.leaf_inds:
            sub_misclass_rate = sub_root.reach_prob * sub_root.compute_error_rate()
            return sub_misclass_rate, [node_index]
        else:
            rem_nodes = [sub_root.left, sub_root.right]
        
        # descending from the given index, and consider adding an error 
        # rate only when a leaf is encountered
        leaf_list = list()
        while len(rem_nodes)>0:
            # the remaining nodes after this iteration will be stored in new_nodes
            new_nodes = []
            for key in rem_nodes:
                node = self.node_dict[str(key)]
                if node.left:
                    new_nodes += [node.left, node.right]
                else:
                    sub_misclass_rate += node.reach_prob*node.compute_error_rate()
                    leaf_list += [key]
            
            rem_nodes = new_nodes
        
        return sub_misclass_rate, leaf_list
    
    def remove_subtree(self, node_index):
        """Removing a subtree rooted at a given node
        
        In order to remove the sub-tree, we start from the given node and go
        down until we encounter all the nodes of the sub-tree. Then, all the
        encountered nodes will be removed from the tree.
        
        Note that the removed nodes should be removed from two parts:
        node dictionary of the tree, leaf list of the tree (if they are
        terminal nodes) 
        """
        
        node_list = list()
        if str(node_index) not in self.node_dict.keys():
            print 'Node %d is not a node of the tree..' % node_index
            return
        elif node_index in self.leaf_inds:
            print 'Node %d is a leaf, nothing to prune..' % node_index
            return
        
        node_list = list()
        root_node = self.node_dict[str(node_index)]
        rem_nodes = [root_node.left, root_node.right]
        while len(rem_nodes)>0:
            # going through the remaining nodes one-by-one and add them 
            # into the next level rem_nodes
            new_rem_nodes = list()
            for node_ind in rem_nodes:
                node_list += [node_ind]
                node_obj = self.node_dict[str(node_ind)]
                if node_obj.left:
                    new_rem_nodes += [node_obj.left, node_obj.right]
            # take the next level of remaining nodes
            rem_nodes = new_rem_nodes
            
        # after encountering all the nodes, remove them from the tree
        for node_ind in node_list:
            del self.node_dict[str(node_ind)]
            if node_ind in self.leaf_inds:
                self.leaf_inds.remove(node_ind)
        
        # finally, the subtree's root should become a leaf itself
        root_node.left = None
        root_node.right = None
        self.leaf_inds += [node_index]
        
        
                    
    def leaf_siblings(self):
        """Returning those leaves with the same parents
        """
        
        siblings = []
        not_visited = copy.deepcopy(self.leaf_inds)
        
        while len(not_visited)>0:
            curr_leaf_ind = not_visited[0]
            # check if the parent has another leaf child
            parent_ind = self.node_dict[str(curr_leaf_ind)].parent
            parent = self.node_dict[str(parent_ind)]
            other_child_ind = parent.right if curr_leaf_ind==parent.left \
                else parent.left
            
            if other_child_ind in not_visited:
                siblings += [[curr_leaf_ind, other_child_ind]]
                # mark them as visited by removing them from not-visited indicator
                not_visited.remove(curr_leaf_ind)
                not_visited.remove(other_child_ind)
            else:
                # only remove the left-index from the not-visited indicator
                not_visited.remove(curr_leaf_ind)
        
        return siblings
    
    def cut_useless_leaves(self):
        """Cutting those leaves whose elimination does not increase the error rate
        """
        
        # only consider the siblings among the leaves
        sibs = self.leaf_siblings()
        
        # check if the error rate of siblings' parents are equal to the average
        # of their own errors 
        sibs_to_remove = []
        for i in range(len(sibs)):
            leaves = sibs[i]
            common_parent = self.node_dict[str(self.node_dict[str(leaves[0])]
                                               .parent)]
            parent_rate = common_parent.compute_error_rate()
            childs = [self.node_dict[str(leaves[0])], 
                      self.node_dict[str(leaves[1])]]
            own_rates = [childs[0].compute_error_rate()*childs[0].reach_prob,
                         childs[1].compute_error_rate()*childs[1].reach_prob]
            av_rate = sum(own_rates) / 2.
            if parent_rate == av_rate:
                sibs_to_remove += sibs[i]
            
        # delete those marked to have same average errors with their parents
        for i in sorted(sibs_to_remove, reverse=True):
            del self.node_dict[str(i)]
            self.leaf_inds.remove(i)
        
        print "%d siblings have been removed from the tree." % len(sibs_to_remove)
    
    def cost_complexity_seq(self):
        """Generating a sequence of trees, using cost-complexity algorithm
        
        The generated sequence starts with the tree itself and ends with the root
        (i.e., a tree with a single node which is the root of the given tree). 
        The sequence is generated such that the i-th tree is a sub-tree of the 
        (i-1)-th tree.
        """
        
        # first cut useless leaves of the tree
        self.cut_useless_leaves()
        
        # start by putting the current tree at the 
        seq_tree = [copy.deepcopy(self)]
        T = copy.deepcopy(self)
        
        # continue till the root is reached
        while len(T.node_dict)>1:
            # compute the critical value for the nodes
            nodes = T.node_dict.keys()
            links = np.ones(len(nodes))
            for i in range(len(nodes)):
                if int(nodes[i]) in T.leaf_inds:
                    links[i] = np.inf
                else:
                    node_error = T.node_dict[nodes[i]].compute_error_rate()
                    sub_error, sub_leaves = self.subtree_props(int(nodes[i]))
                    
                    if sub_error > node_error:
                        raise ValueError('Something went wrong: error rate of' +
                                         ' a subtree cannot be larger than its root')
                    elif len(sub_leaves)==1:
                        #pdb.set_trace()
                        raise ValueError('Somethin went wrong: number of leaves of' +
                                         'a subtree rooted at a non-leaf node' +
                                         ' cannot be 1')
                    
                    links[i] = (node_error - sub_error) / float(len(sub_leaves) - 1)
                
            # remove the sub-tree with the weakest link
            weakest_link = np.argmin(links)
            T.remove_subtree(int(nodes[weakest_link]))
            
            seq_tree += [copy.deepcopy(T)]
            #pdb.set_trace()
            
        return seq_tree

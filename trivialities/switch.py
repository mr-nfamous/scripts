if __name__ == '__main__':
    def uninit_switch(*args):
        raise TypeError("executed a case stmt outside switch's context")

    class switch:

        @property
        def default(self):
            if self.finished:
                raise SyntaxError("multiple 'default' cases were provided")
            self.finished = True
            return True
        
        def __init__(self, target):        
            self.__targ = target
            self.compare = uninit_switch

        def __iter__(self):
            self.islocked = True # when True, must test for equality on each
            self.finished = False # default has been evaluated
            
            def cmp_unlocked(targ):
                assert not self.islocked
                if self.finished:
                    raise SyntaxError("switch continued after execution of default")
                return True
            
            def cmp_locked(targ, cmp=self.__targ.__eq__):
                assert self.islocked
                if self.islocked and cmp(targ):
                    self.islocked = False
                    self.compare = cmp_unlocked
                    return True
                return False

            self.compare = cmp_locked
            yield self
                
        def __call__(self, comp):
            return self.compare(comp)
            
    def switch_demo(x):
        for case in switch(x):
            if case(-1): print('below zero')
            case(0);
            if case(1): print(1)
            if case(2): print(2)
            case.default
            print('default')
    switch_demo(1)

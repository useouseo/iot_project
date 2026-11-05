#include <cassert>
#include <vector>
#include "../firmware/include/direction.h"
int run(std::vector<int> masks, unsigned step=100){DirectionCounter c;int n=0;unsigned time=0;for(int m:masks){n+=c.update(m&1,m&2,time);time+=step;}return n;}
int main(){
 assert(run({0,1,3,2,0})==1);
 assert(run({0,2,3,1,0})==-1);
 assert(run({0,1,1,3,3,2,2,0})==1);
 assert(run({0,1,0})==0);
 assert(run({0,1,3,1,0})==0);
 assert(run({0,3,0})==0);
 assert(run({0,1,2,0})==0);
 assert(run({0,1,3,2,0},1200)==0);
 assert(run({0,1,0,1,3,2,0})==1);
 assert(run({0,1,3,2,0,2,3,1,0})==0);
 DirectionCounter c;c.update(true,false,1);c.invalidate();c.update(true,true,2);c.update(false,false,3);
 assert(c.update(true,false,4)==0);c.update(true,true,5);c.update(false,true,6);assert(c.update(false,false,7)==1);
}

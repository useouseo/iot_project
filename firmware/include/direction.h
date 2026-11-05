#pragma once
#include <stdint.h>
// Full traversal only: 00 -> A -> AB -> B -> 00, or the exact reverse.
// Any reverse/skip/timeout invalidates the path until BOTH zones are clear.
class DirectionCounter {
  int state_ = -1;
  int last_ = 0;
  uint32_t start_ = 0;
 public:
  void invalidate() { state_ = -1; }
  int update(bool a, bool b, uint32_t now) {
    int mask=(a?1:0)|(b?2:0);
    if(state_ && state_!=-1 && uint32_t(now-start_)>3500)state_=-1;
    if(state_==-1) { if(mask==0){state_=0;last_=0;}return 0; }
    if(mask==last_)return 0;
    last_=mask;
    if(state_==0){if(mask==1){state_=1;start_=now;}else if(mask==2){state_=4;start_=now;}else if(mask)state_=-1;}
    else if(state_==1)state_=(mask==3)?2:-1;
    else if(state_==2)state_=(mask==2)?3:-1;
    else if(state_==3){if(mask==0){state_=0;return 1;}state_=-1;}
    else if(state_==4)state_=(mask==3)?5:-1;
    else if(state_==5)state_=(mask==1)?6:-1;
    else if(state_==6){if(mask==0){state_=0;return -1;}state_=-1;}
    // The invalidating transition may itself already be clear.
    if(state_==-1 && mask==0){state_=0;last_=0;}
    return 0;
  }
};

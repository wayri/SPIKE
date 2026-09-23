#pragma once
#include <array>
#include <cmath>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>

namespace spikes {
struct BehavioralValue { double value{}; std::array<double,32> gradient{}; };
/** Bounded, validated expression DAG. No host callbacks, files or executable code. */
class BehavioralProgram {
  struct Node {std::string op; int a,b,c; double value;};
  std::vector<Node> nodes_;
public:
  const std::string serialized;
  explicit BehavioralProgram(const std::string& text):serialized(text) {
    if(text.size()>65536) throw std::invalid_argument("behavioral program too large");
    std::istringstream input(text);Node n;
    while(input>>n.op) {
      if(!(input>>n.a>>n.b>>n.c>>n.value)||!std::isfinite(n.value)) throw std::invalid_argument("invalid behavioral instruction");
      const std::string unary=" neg abs acos acosh asin asinh atan cos cosh ceil exp floor int log log10 sgn sin sinh sqrt tanh u uramp ";
      const std::string binary=" add sub mul div mod pow atan2 hypot max min gt ge lt le ";
      int arity=n.op=="const"||n.op=="signal"||n.op=="time"?0:(unary.find(" "+n.op+" ")!=std::string::npos?1:(binary.find(" "+n.op+" ")!=std::string::npos?2:((n.op=="if"||n.op=="limit")?3:-1)));
      if(arity<0 || nodes_.size()>=512) throw std::invalid_argument("unsupported behavioral opcode or size");
      const int indices[]{n.a,n.b,n.c};
      for(int i=0;i<3;++i) if(i<arity ? (indices[i]<0||static_cast<std::size_t>(indices[i])>=nodes_.size()) : indices[i]!=-1) throw std::invalid_argument("invalid behavioral DAG reference");
      if(n.op=="signal" && (n.value<0||n.value>=32||std::floor(n.value)!=n.value)) throw std::invalid_argument("invalid behavioral signal index");
      nodes_.push_back(n);
    }
    if(nodes_.empty()) throw std::invalid_argument("empty behavioral program");
  }
  BehavioralValue evaluate(const std::vector<double>& signals,double time=0.) const {
    if(signals.size()>32) throw std::invalid_argument("too many behavioral signals");
    std::vector<BehavioralValue> cache(nodes_.size());std::vector<bool> ready(nodes_.size(),false);
    std::function<BehavioralValue(int)> eval=[&](int i)->BehavioralValue {
      if(ready[i]) return cache[i];const auto& n=nodes_[i];BehavioralValue r;
      if(n.op=="const") r.value=n.value;
      else if(n.op=="time") r.value=time;
      else if(n.op=="signal") {const auto k=static_cast<std::size_t>(n.value);r.value=signals.at(k);r.gradient[k]=1;}
      else {
        const auto a=eval(n.a);const double x=a.value;
        if(n.op=="if") r=eval(x!=0?n.b:n.c); // Lazy branches: invalid inactive domains are never evaluated.
        else {
          const auto b=n.b>=0?eval(n.b):BehavioralValue{};const double y=b.value;
          double da=0,db=0;
          if(n.op=="limit") {auto c=eval(n.c);if(y>=c.value) throw std::invalid_argument("limit lower bound must be smaller");r=x<y?b:(x>c.value?c:a);}
          else {
            if(n.op=="add") {r.value=x+y;da=1;db=1;}
            else if(n.op=="sub") {r.value=x-y;da=1;db=-1;}
            else if(n.op=="mul") {r.value=x*y;da=y;db=x;}
            else if(n.op=="div") {r.value=x/y;da=1/y;db=-x/(y*y);}
            else if(n.op=="mod") {r.value=x-std::floor(x/y)*y;da=1;db=-std::floor(x/y);}
            else if(n.op=="pow") {r.value=std::pow(x,y);da=y==0?0:y*std::pow(x,y-1);if(x>0)db=r.value*std::log(x);else if(std::any_of(b.gradient.begin(),b.gradient.end(),[](double d){return d!=0;}))throw std::invalid_argument("nonpositive power base with variable exponent");}
            else if(n.op=="max"||n.op=="min") {r=(n.op=="max"?x>=y:x<=y)?a:b;}
            else if(n.op=="gt"||n.op=="ge"||n.op=="lt"||n.op=="le") {r.value=n.op=="gt"?x>y:n.op=="ge"?x>=y:n.op=="lt"?x<y:x<=y;}
            else if(n.op=="atan2") {r.value=std::atan2(x,y);da=y/(x*x+y*y);db=-x/(x*x+y*y);}
            else if(n.op=="hypot") {r.value=std::hypot(x,y);da=r.value==0?0:x/r.value;db=r.value==0?0:y/r.value;}
            else if(n.op=="neg") {r.value=-x;da=-1;}
            else if(n.op=="abs") {r.value=std::abs(x);da=x>0?1:x<0?-1:0;}
            else if(n.op=="sin") {r.value=std::sin(x);da=std::cos(x);}
            else if(n.op=="cos") {r.value=std::cos(x);da=-std::sin(x);}
            else if(n.op=="sinh") {r.value=std::sinh(x);da=std::cosh(x);}
            else if(n.op=="cosh") {r.value=std::cosh(x);da=std::sinh(x);}
            else if(n.op=="tanh") {r.value=std::tanh(x);da=1-r.value*r.value;}
            else if(n.op=="exp") {r.value=std::exp(x);da=r.value;}
            else if(n.op=="log"||n.op=="log10") {r.value=n.op=="log"?std::log(x):std::log10(x);da=(n.op=="log"?1:1/std::log(10.))/x;}
            else if(n.op=="sqrt") {r.value=std::sqrt(x);da=.5/r.value;}
            else if(n.op=="atan") {r.value=std::atan(x);da=1/(1+x*x);}
            else if(n.op=="asin") {r.value=std::asin(x);da=1/std::sqrt(1-x*x);}
            else if(n.op=="acos") {r.value=std::acos(x);da=-1/std::sqrt(1-x*x);}
            else if(n.op=="asinh") {r.value=std::asinh(x);da=1/std::sqrt(1+x*x);}
            else if(n.op=="acosh") {r.value=std::acosh(x);da=1/std::sqrt(x*x-1);}
            else if(n.op=="floor") r.value=std::floor(x);
            else if(n.op=="ceil") r.value=std::ceil(x);
            else if(n.op=="int") r.value=std::trunc(x);
            else if(n.op=="sgn") r.value=x>0?1:x<0?-1:0;
            else if(n.op=="u") r.value=x>=0?1:0;
            else if(n.op=="uramp") {r.value=std::max(0.,x);da=x>0?1:0;}
            for(std::size_t k=0;k<signals.size();++k) r.gradient[k]+=(a.gradient[k]==0?0:da*a.gradient[k])+(b.gradient[k]==0?0:db*b.gradient[k]);
          }
        }
      }
      if(!std::isfinite(r.value)||std::any_of(r.gradient.begin(),r.gradient.end(),[](double d){return !std::isfinite(d);})) throw std::invalid_argument("behavioral value/derivative outside finite mathematical domain");
      ready[i]=true;return cache[i]=r;
    };
    return eval(static_cast<int>(nodes_.size()-1));
  }
};
}

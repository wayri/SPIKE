// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace spikes {
struct BehavioralValue { double value{}; std::array<double,32> gradient{}; };
/** Bounded, validated expression DAG. No host callbacks, files or executable code. */
class BehavioralProgram {
  enum class Opcode : std::uint8_t {
    constant, signal, time,
    neg, abs, acos, acosh, asin, asinh, atan, atanh, cos, cosh, ceil, exp,
    floor, integer, log, log10, sgn, sin, sinh, sqrt, tan, tanh, u, uramp,
    add, sub, mul, div, mod, pow, atan2, hypot, max, min, gt, ge, lt, le,
    if_, limit, invalid,
  };
  struct Node {Opcode op; int a,b,c; double value;};
  struct EvaluationScratch {
    std::array<BehavioralValue,512> cache{};
    std::array<std::uint64_t,512> ready_generation{};
    std::uint64_t generation{};

    std::uint64_t next_generation() {
      ++generation;
      if(generation==0) {
        ready_generation.fill(0);
        generation=1;
      }
      return generation;
    }
  };
  std::vector<Node> nodes_;

  static Opcode opcode(std::string_view name) {
    if(name=="const") return Opcode::constant;
    if(name=="signal") return Opcode::signal;
    if(name=="time") return Opcode::time;
    if(name=="neg") return Opcode::neg;
    if(name=="abs") return Opcode::abs;
    if(name=="acos") return Opcode::acos;
    if(name=="acosh") return Opcode::acosh;
    if(name=="asin") return Opcode::asin;
    if(name=="asinh") return Opcode::asinh;
    if(name=="atan") return Opcode::atan;
    if(name=="atanh") return Opcode::atanh;
    if(name=="cos") return Opcode::cos;
    if(name=="cosh") return Opcode::cosh;
    if(name=="ceil") return Opcode::ceil;
    if(name=="exp") return Opcode::exp;
    if(name=="floor") return Opcode::floor;
    if(name=="int") return Opcode::integer;
    if(name=="log") return Opcode::log;
    if(name=="log10") return Opcode::log10;
    if(name=="sgn") return Opcode::sgn;
    if(name=="sin") return Opcode::sin;
    if(name=="sinh") return Opcode::sinh;
    if(name=="sqrt") return Opcode::sqrt;
    if(name=="tan") return Opcode::tan;
    if(name=="tanh") return Opcode::tanh;
    if(name=="u") return Opcode::u;
    if(name=="uramp") return Opcode::uramp;
    if(name=="add") return Opcode::add;
    if(name=="sub") return Opcode::sub;
    if(name=="mul") return Opcode::mul;
    if(name=="div") return Opcode::div;
    if(name=="mod") return Opcode::mod;
    if(name=="pow") return Opcode::pow;
    if(name=="atan2") return Opcode::atan2;
    if(name=="hypot") return Opcode::hypot;
    if(name=="max") return Opcode::max;
    if(name=="min") return Opcode::min;
    if(name=="gt") return Opcode::gt;
    if(name=="ge") return Opcode::ge;
    if(name=="lt") return Opcode::lt;
    if(name=="le") return Opcode::le;
    if(name=="if") return Opcode::if_;
    if(name=="limit") return Opcode::limit;
    return Opcode::invalid;
  }
  static int arity(Opcode op) {
    switch(op) {
      case Opcode::constant: case Opcode::signal: case Opcode::time: return 0;
      case Opcode::neg: case Opcode::abs: case Opcode::acos: case Opcode::acosh:
      case Opcode::asin: case Opcode::asinh: case Opcode::atan: case Opcode::atanh:
      case Opcode::cos: case Opcode::cosh: case Opcode::ceil: case Opcode::exp:
      case Opcode::floor: case Opcode::integer: case Opcode::log: case Opcode::log10:
      case Opcode::sgn: case Opcode::sin: case Opcode::sinh: case Opcode::sqrt:
      case Opcode::tan: case Opcode::tanh: case Opcode::u: case Opcode::uramp: return 1;
      case Opcode::add: case Opcode::sub: case Opcode::mul: case Opcode::div:
      case Opcode::mod: case Opcode::pow: case Opcode::atan2: case Opcode::hypot:
      case Opcode::max: case Opcode::min: case Opcode::gt: case Opcode::ge:
      case Opcode::lt: case Opcode::le: return 2;
      case Opcode::if_: case Opcode::limit: return 3;
      case Opcode::invalid: return -1;
    }
    return -1;
  }
public:
  const std::string serialized;
  explicit BehavioralProgram(const std::string& text):serialized(text) {
    if(text.size()>65536) throw std::invalid_argument("behavioral program too large");
    std::istringstream input(text);std::string name;int a,b,c;double value;
    while(input>>name) {
      if(!(input>>a>>b>>c>>value)||!std::isfinite(value)) throw std::invalid_argument("invalid behavioral instruction");
      const auto op=opcode(name);const int count=arity(op);
      if(count<0 || nodes_.size()>=512) throw std::invalid_argument("unsupported behavioral opcode or size");
      const int indices[]{a,b,c};
      for(int i=0;i<3;++i) if(i<count ? (indices[i]<0||static_cast<std::size_t>(indices[i])>=nodes_.size()) : indices[i]!=-1) throw std::invalid_argument("invalid behavioral DAG reference");
      if(op==Opcode::signal && (value<0||value>=32||std::floor(value)!=value)) throw std::invalid_argument("invalid behavioral signal index");
      nodes_.push_back(Node{op,a,b,c,value});
    }
    if(nodes_.empty()) throw std::invalid_argument("empty behavioral program");
  }
  BehavioralValue evaluate(const std::vector<double>& signals,double time=0.) const {
    if(signals.size()>32) throw std::invalid_argument("too many behavioral signals");
    static thread_local EvaluationScratch scratch;
    const auto generation=scratch.next_generation();
    const auto eval=[&](auto&& self,int i)->BehavioralValue {
      if(scratch.ready_generation[i]==generation) return scratch.cache[i];
      const auto& n=nodes_[i];BehavioralValue r;
      if(n.op==Opcode::constant) r.value=n.value;
      else if(n.op==Opcode::time) r.value=time;
      else if(n.op==Opcode::signal) {const auto k=static_cast<std::size_t>(n.value);r.value=signals.at(k);r.gradient[k]=1;}
      else {
        const auto a=self(self,n.a);const double x=a.value;
        if(n.op==Opcode::if_) r=self(self,x!=0?n.b:n.c); // Lazy branches: invalid inactive domains are never evaluated.
        else {
          const auto b=n.b>=0?self(self,n.b):BehavioralValue{};const double y=b.value;
          double da=0,db=0;
          if(n.op==Opcode::limit) {auto c=self(self,n.c);if(y>=c.value) throw std::invalid_argument("limit lower bound must be smaller");r=x<y?b:(x>c.value?c:a);}
          else {
            switch(n.op) {
              case Opcode::add: r.value=x+y;da=1;db=1;break;
              case Opcode::sub: r.value=x-y;da=1;db=-1;break;
              case Opcode::mul: r.value=x*y;da=y;db=x;break;
              case Opcode::div: r.value=x/y;da=1/y;db=-x/(y*y);break;
              case Opcode::mod: r.value=x-std::floor(x/y)*y;da=1;db=-std::floor(x/y);break;
              case Opcode::pow:
                r.value=std::pow(x,y);da=y==0?0:y*std::pow(x,y-1);
                if(x>0) db=r.value*std::log(x);
                else if(std::any_of(b.gradient.begin(),b.gradient.end(),[](double d){return d!=0;})) throw std::invalid_argument("nonpositive power base with variable exponent");
                break;
              case Opcode::max: r=x>=y?a:b;break;
              case Opcode::min: r=x<=y?a:b;break;
              case Opcode::gt: r.value=x>y;break;
              case Opcode::ge: r.value=x>=y;break;
              case Opcode::lt: r.value=x<y;break;
              case Opcode::le: r.value=x<=y;break;
              case Opcode::atan2: r.value=std::atan2(x,y);da=y/(x*x+y*y);db=-x/(x*x+y*y);break;
              case Opcode::hypot: r.value=std::hypot(x,y);da=r.value==0?0:x/r.value;db=r.value==0?0:y/r.value;break;
              case Opcode::neg: r.value=-x;da=-1;break;
              case Opcode::abs: r.value=std::abs(x);da=x>0?1:x<0?-1:0;break;
              case Opcode::sin: r.value=std::sin(x);da=std::cos(x);break;
              case Opcode::cos: r.value=std::cos(x);da=-std::sin(x);break;
              case Opcode::tan: r.value=std::tan(x);da=1+r.value*r.value;break;
              case Opcode::atanh:
                if(std::abs(x)>=1) throw std::invalid_argument("atanh requires absolute argument below one");
                r.value=std::atanh(x);da=1/(1-x*x);break;
              case Opcode::sinh: r.value=std::sinh(x);da=std::cosh(x);break;
              case Opcode::cosh: r.value=std::cosh(x);da=std::sinh(x);break;
              case Opcode::tanh: r.value=std::tanh(x);da=1-r.value*r.value;break;
              case Opcode::exp: r.value=std::exp(x);da=r.value;break;
              case Opcode::log: r.value=std::log(x);da=1/x;break;
              case Opcode::log10: r.value=std::log10(x);da=(1/std::log(10.))/x;break;
              case Opcode::sqrt: r.value=std::sqrt(x);da=.5/r.value;break;
              case Opcode::atan: r.value=std::atan(x);da=1/(1+x*x);break;
              case Opcode::asin: r.value=std::asin(x);da=1/std::sqrt(1-x*x);break;
              case Opcode::acos: r.value=std::acos(x);da=-1/std::sqrt(1-x*x);break;
              case Opcode::asinh: r.value=std::asinh(x);da=1/std::sqrt(1+x*x);break;
              case Opcode::acosh: r.value=std::acosh(x);da=1/std::sqrt(x*x-1);break;
              case Opcode::floor: r.value=std::floor(x);break;
              case Opcode::ceil: r.value=std::ceil(x);break;
              case Opcode::integer: r.value=std::trunc(x);break;
              case Opcode::sgn: r.value=x>0?1:x<0?-1:0;break;
              case Opcode::u: r.value=x>=0?1:0;break;
              case Opcode::uramp: r.value=std::max(0.,x);da=x>0?1:0;break;
              default: break;
            }
            for(std::size_t k=0;k<signals.size();++k) r.gradient[k]+=(a.gradient[k]==0?0:da*a.gradient[k])+(b.gradient[k]==0?0:db*b.gradient[k]);
          }
        }
      }
      if(!std::isfinite(r.value)||std::any_of(r.gradient.begin(),r.gradient.end(),[](double d){return !std::isfinite(d);})) throw std::invalid_argument("behavioral value/derivative outside finite mathematical domain");
      scratch.ready_generation[i]=generation;return scratch.cache[i]=r;
    };
    return eval(eval,static_cast<int>(nodes_.size()-1));
  }
};
}

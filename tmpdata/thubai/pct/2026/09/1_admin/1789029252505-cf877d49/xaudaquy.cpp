#include <bits/stdc++.h>
#define ll long long
using namespace std;

int main(){
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    freopen("xaudaquy.inp", "r", stdin);
    freopen("xaudaquy.out", "w", stdout);
    string a;
    cin>>a;
    ll d=0;
    ll t=a.size();
    for(ll i=0;i<t;i++){
        string tmp=a.substr(i,t-i);
        string tmp2=a.substr(0,i);
        string tmp3=tmp+tmp2;
        string rev=tmp3;
        reverse(rev.begin(),rev.end());
        if(tmp3==rev){
            d++;
        }
    }
    cout<<d;
    return 0;
}
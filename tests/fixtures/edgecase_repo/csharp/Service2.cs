using System;

namespace Example.Gen
{
    public interface IHandler2
    {
        bool Handle(string payload);
    }

    public class Base2
    {
        protected string Name;
    }

    public class Service2 : Base2, IHandler2
    {
        public Service2(string name)
        {
            this.Name = name;
        }

        public bool Handle(string payload)
        {
            this.Validate(payload);
            return true;
        }

        private void Validate(string payload) { }
    }
}
